from backend.schemas.lineup_scenarios.lineup_scenarios import (
    LineupScenarioDefinition,
    LineupScenarioTeamFlag,
    UploadedLineup,
    UploadedLineupPlayer,
)
from backend.services.lineup_scenarios.lineup_scenario_engine import evaluate_scenario, evaluate_scenarios


def _lineup(index, team_by_position, depth_slot_by_slot=None):
    """team_by_position maps roster slot -> team (e.g. "QB": "BUF").
    depth_slot_by_slot optionally overrides the resolved `depth_slot` per
    slot (defaults to the slot name itself with rank 1, e.g. a "RB" slot
    resolves to depth_slot "RB1") -- lets tests put a skill player in a
    "FLEX" slot with an explicit depth slot, mirroring the FLEX ambiguity
    this feature exists to handle."""
    depth_slot_by_slot = depth_slot_by_slot or {}
    players = [
        UploadedLineupPlayer(
            roster_position=pos,
            name=f"{pos} Player",
            team=team,
            position=pos,
            depth_slot=depth_slot_by_slot.get(pos, f"{pos}1"),
        )
        for pos, team in team_by_position.items()
    ]
    return UploadedLineup(index=index, players=players)


def _flag(team, role="any", positions=None):
    return LineupScenarioTeamFlag(team=team, role=role, positions=positions or [])


def test_single_team_scenario_satisfied_when_count_meets_min_stack():
    lineup = _lineup(1, {"QB": "BUF", "RB": "BUF", "WR": "KC"})
    scenario = LineupScenarioDefinition(label="BUF stack", team_flags=[_flag("BUF")])
    match = evaluate_scenario(lineup, scenario, min_stack_size=2)
    assert match.satisfied is True
    assert match.team_stacks == [match.team_stacks[0]]
    assert match.team_stacks[0].team == "BUF"
    assert match.team_stacks[0].role == "any"
    assert match.team_stacks[0].count == 2
    assert match.team_stacks[0].satisfied is True


def test_multi_team_scenario_requires_every_team_to_clear_threshold():
    lineup = _lineup(1, {"QB": "BUF", "RB": "BUF", "WR": "KC", "TE": "SF"})
    scenario = LineupScenarioDefinition(label="BUF and KC both go off", team_flags=[_flag("BUF"), _flag("KC")])
    match = evaluate_scenario(lineup, scenario, min_stack_size=2)
    assert match.satisfied is False
    stacks_by_team = {s.team: s for s in match.team_stacks}
    assert stacks_by_team["BUF"].count == 2 and stacks_by_team["BUF"].satisfied is True
    assert stacks_by_team["KC"].count == 1 and stacks_by_team["KC"].satisfied is False


def test_unsatisfiable_scenario_for_team_not_in_lineup():
    lineup = _lineup(1, {"QB": "BUF", "RB": "BUF"})
    scenario = LineupScenarioDefinition(label="Never happens", team_flags=[_flag("MIA")])
    match = evaluate_scenario(lineup, scenario, min_stack_size=1)
    assert match.satisfied is False
    assert match.team_stacks[0].count == 0


def test_min_stack_size_changes_the_outcome_for_the_same_lineup():
    lineup = _lineup(1, {"QB": "BUF", "RB": "BUF", "WR": "KC"})
    scenario = LineupScenarioDefinition(label="BUF stack", team_flags=[_flag("BUF")])
    match_1 = evaluate_scenario(lineup, scenario, min_stack_size=1)
    match_2 = evaluate_scenario(lineup, scenario, min_stack_size=2)
    match_3 = evaluate_scenario(lineup, scenario, min_stack_size=3)
    assert match_1.satisfied is True
    assert match_2.satisfied is True
    assert match_3.satisfied is False


def test_evaluate_scenarios_returns_one_result_per_lineup_with_matches_in_order():
    lineups = [
        _lineup(1, {"QB": "BUF", "RB": "BUF"}),
        _lineup(2, {"QB": "KC", "RB": "KC"}),
    ]
    scenarios = [
        LineupScenarioDefinition(label="BUF stack", team_flags=[_flag("BUF")]),
        LineupScenarioDefinition(label="KC stack", team_flags=[_flag("KC")]),
    ]
    results = evaluate_scenarios(lineups, scenarios, min_stack_size=2)
    assert len(results) == 2
    assert [m.label for m in results[0].matches] == ["BUF stack", "KC stack"]
    assert results[0].matches[0].satisfied is True
    assert results[0].matches[1].satisfied is False
    assert results[1].matches[0].satisfied is False
    assert results[1].matches[1].satisfied is True


def test_positions_filter_restricts_count_to_matching_depth_slots_only():
    # Same team, same lineup -- but the BUF starting RB is rostered in a
    # FLEX slot, so a naive roster_position check would miss it. Resolved
    # `depth_slot` (not roster_position, and not the coarser `position`) is
    # what the positions filter must check.
    lineup = _lineup(
        1,
        {"QB": "BUF", "FLEX": "BUF", "WR": "BUF"},
        depth_slot_by_slot={"FLEX": "RB1"},
    )
    scenario_any_position = LineupScenarioDefinition(label="BUF stack", team_flags=[_flag("BUF")])
    scenario_rb1_only = LineupScenarioDefinition(
        label="BUF starting RB only", team_flags=[_flag("BUF", role="positive_script", positions=["RB1"])]
    )

    match_any = evaluate_scenario(lineup, scenario_any_position, min_stack_size=2)
    match_rb1_only = evaluate_scenario(lineup, scenario_rb1_only, min_stack_size=2)

    assert match_any.team_stacks[0].count == 3
    assert match_rb1_only.team_stacks[0].count == 1
    assert match_rb1_only.team_stacks[0].satisfied is False
    assert match_rb1_only.team_stacks[0].role == "positive_script"
    assert match_rb1_only.team_stacks[0].positions == ["RB1"]


def test_multiple_flags_for_the_same_team_are_evaluated_independently():
    # A caller can flag the same team more than once within one scenario to
    # combine roles -- e.g. this team's starting RB AND its top-2 WRs, both
    # of which must independently clear the threshold.
    lineup = _lineup(
        1,
        {"QB": "BUF", "RB": "BUF", "WR": "BUF", "WR2": "BUF", "TE": "BUF"},
        depth_slot_by_slot={"WR": "WR1", "WR2": "WR2"},
    )
    scenario = LineupScenarioDefinition(
        label="BUF RB1 and 2+ WR1s",
        team_flags=[
            _flag("BUF", role="positive_script", positions=["RB1"]),
            _flag("BUF", role="pass_funnel", positions=["WR1", "WR2"]),
        ],
    )
    match = evaluate_scenario(lineup, scenario, min_stack_size=1)
    assert len(match.team_stacks) == 2
    assert match.team_stacks[0].role == "positive_script" and match.team_stacks[0].count == 1
    assert match.team_stacks[1].role == "pass_funnel" and match.team_stacks[1].count == 2
    assert match.satisfied is True
