"""
Pure stack-counting against each uploaded lineup's already-team-resolved
players (see team_resolution.py) -- no fantasy-point projection math
anywhere in this feature, unlike Contest Results' optimal-lineup scoring.
A scenario flags one or more teams, each with a caller-assigned role
(purely descriptive -- see ScenarioRole's own docstring) and an optional
`positions` filter; a lineup "satisfies" a scenario when EVERY flagged
team has at least `min_stack_size` rostered players THAT MATCH THAT
TEAM'S OWN positions FILTER (or any position, if the filter is empty).
"""

from __future__ import annotations

from backend.schemas.lineup_scenarios.lineup_scenarios import (
    LineupScenarioDefinition,
    LineupScenarioMatch,
    LineupScenarioResult,
    ScenarioTeamStack,
    UploadedLineup,
)


def _matching_player_count(lineup: UploadedLineup, team: str, positions: list[str]) -> int:
    """How many of this lineup's rostered players resolved to `team` AND
    (positions is empty, meaning "any position counts", or that player's
    own resolved `depth_slot` -- e.g. "RB1"/"WR2", not the coarser
    `position` or the uploaded CSV's own `roster_position` -- is in
    positions). Checking depth_slot rather than position is what lets a
    scenario flag distinguish "this team's starting RB" from "any of this
    team's RBs" -- see UploadedLineupPlayer.depth_slot's own docstring.
    Ignores any player whose team never resolved (team is None -- see
    team_resolution.py)."""
    return sum(
        1
        for player in lineup.players
        if player.team == team and (not positions or player.depth_slot in positions)
    )


def evaluate_scenario(
    lineup: UploadedLineup, scenario: LineupScenarioDefinition, min_stack_size: int
) -> LineupScenarioMatch:
    """A scenario is satisfied only if EVERY one of its own flagged teams
    clears min_stack_size in this lineup, counting only players that match
    that flag's own `positions` filter (if any) -- e.g. a "BUF and KC both
    go off" scenario needs min_stack_size matching players from BUF *and*
    min_stack_size from KC, not either/or. A team with zero matching
    players in this lineup still gets its own ScenarioTeamStack entry
    (count=0, satisfied=False) so the frontend's hover breakdown always
    shows every flagged team, not just the ones that showed up."""
    team_stacks = [
        ScenarioTeamStack(
            team=flag.team,
            role=flag.role,
            positions=flag.positions,
            count=_matching_player_count(lineup, flag.team, flag.positions),
            satisfied=_matching_player_count(lineup, flag.team, flag.positions) >= min_stack_size,
        )
        for flag in scenario.team_flags
    ]
    satisfied = all(stack.satisfied for stack in team_stacks)
    return LineupScenarioMatch(label=scenario.label, satisfied=satisfied, team_stacks=team_stacks)


def evaluate_scenarios(
    lineups: list[UploadedLineup], scenarios: list[LineupScenarioDefinition], min_stack_size: int
) -> list[LineupScenarioResult]:
    """One LineupScenarioResult per lineup, each carrying one
    LineupScenarioMatch per scenario in the same order `scenarios` was
    passed in, so callers can render one results column per scenario
    without re-sorting."""
    return [
        LineupScenarioResult(
            lineup=lineup,
            matches=[evaluate_scenario(lineup, scenario, min_stack_size) for scenario in scenarios],
        )
        for lineup in lineups
    ]
