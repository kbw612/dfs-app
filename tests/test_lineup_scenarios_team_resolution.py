from backend.schemas.depth_charts.snapshot import Player as DepthChartPlayer
from backend.schemas.depth_charts.snapshot import Snapshot as DepthChartSnapshot
from backend.schemas.depth_charts.snapshot import Team as DepthChartTeam
from backend.schemas.lineup_scenarios.lineup_scenarios import UploadedLineup, UploadedLineupPlayer
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.lineup_scenarios.team_resolution import resolve_lineup_teams


def _salary_player(player, position, team):
    return OwnershipPlayer(player=player, position=position, team=team, opponent="OPP", salary=6000)


def _salary_players():
    return [
        _salary_player("Josh Allen", "QB", "BUF"),
        _salary_player("D.J. Moore", "WR", "CHI"),
        _salary_player("James Cook", "RB", "BUF"),
        _salary_player("Ray Davis", "RB", "BUF"),
        _salary_player("Las Vegas Raiders", "DST", "LV"),
    ]


def _depth_chart_snapshot():
    return DepthChartSnapshot(
        scraped_at="2026-09-01T08:00:00-04:00",
        source_url="https://example.com",
        teams=[
            DepthChartTeam(
                team_name="Buffalo Bills",
                team_abbrev="BUF",
                positions={
                    "QB": [DepthChartPlayer(player="Josh Allen")],
                    "RB": [DepthChartPlayer(player="James Cook"), DepthChartPlayer(player="Ray Davis")],
                    "WR": [DepthChartPlayer(player="D.J. Moore")],
                },
            )
        ],
    )


def test_resolves_matching_names_case_insensitively():
    lineup = UploadedLineup(
        index=1,
        players=[
            UploadedLineupPlayer(roster_position="QB", name="josh allen", team=None),
            UploadedLineupPlayer(roster_position="DST", name="Las Vegas Raiders", team=None),
        ],
    )
    resolved, unresolved = resolve_lineup_teams([lineup], _salary_players())
    teams = [p.team for p in resolved[0].players]
    assert teams == ["BUF", "LV"]
    assert unresolved == []


def test_resolves_position_alongside_team():
    lineup = UploadedLineup(
        index=1,
        players=[
            UploadedLineupPlayer(roster_position="QB", name="josh allen", team=None),
            UploadedLineupPlayer(roster_position="FLEX", name="D.J. Moore", team=None),
        ],
    )
    resolved, _unresolved = resolve_lineup_teams([lineup], _salary_players())
    positions = [p.position for p in resolved[0].players]
    assert positions == ["QB", "WR"]


def test_leaves_unmatched_name_team_and_position_none_and_reports_it():
    lineup = UploadedLineup(
        index=1,
        players=[
            UploadedLineupPlayer(roster_position="WR", name="Nobody Real", team=None),
        ],
    )
    resolved, unresolved = resolve_lineup_teams([lineup], _salary_players())
    assert resolved[0].players[0].team is None
    assert resolved[0].players[0].position is None
    assert unresolved == ["Nobody Real"]


def test_dedupes_unresolved_names_across_lineups():
    lineups = [
        UploadedLineup(index=1, players=[UploadedLineupPlayer(roster_position="WR", name="Nobody Real", team=None)]),
        UploadedLineup(index=2, players=[UploadedLineupPlayer(roster_position="WR", name="Nobody Real", team=None)]),
    ]
    _resolved, unresolved = resolve_lineup_teams(lineups, _salary_players())
    assert unresolved == ["Nobody Real"]


def test_resolves_depth_slot_for_skill_positions_from_depth_chart_snapshot():
    lineup = UploadedLineup(
        index=1,
        players=[
            UploadedLineupPlayer(roster_position="QB", name="Josh Allen", team=None),
            UploadedLineupPlayer(roster_position="RB", name="James Cook", team=None),
            UploadedLineupPlayer(roster_position="FLEX", name="Ray Davis", team=None),
            UploadedLineupPlayer(roster_position="DST", name="Las Vegas Raiders", team=None),
        ],
    )
    resolved, _unresolved = resolve_lineup_teams([lineup], _salary_players(), _depth_chart_snapshot())
    depth_slots = [p.depth_slot for p in resolved[0].players]
    # James Cook is BUF's RB1 (first in the depth chart's RB list), Ray
    # Davis is RB2, regardless of which uploaded roster slot (RB vs FLEX)
    # they were rostered in. DST always resolves to the fixed "DST" slot,
    # never a ranked one -- there's only one defense per team.
    assert depth_slots == ["QB1", "RB1", "RB2", "DST"]


def test_depth_slot_is_none_without_a_depth_chart_snapshot():
    lineup = UploadedLineup(
        index=1,
        players=[UploadedLineupPlayer(roster_position="QB", name="Josh Allen", team=None)],
    )
    resolved, _unresolved = resolve_lineup_teams([lineup], _salary_players(), depth_snapshot=None)
    assert resolved[0].players[0].depth_slot is None


def test_depth_slot_is_none_when_player_not_on_any_depth_chart():
    # D.J. Moore resolves a team/position from the salary snapshot, but
    # isn't listed on the fake depth chart's own WR group here -- keeps
    # depth_slot None rather than guessing, same "unknown, not wrong"
    # convention as an unmatched name entirely.
    lineup = UploadedLineup(
        index=1,
        players=[UploadedLineupPlayer(roster_position="WR", name="D.J. Moore", team=None)],
    )
    empty_depth_chart = DepthChartSnapshot(scraped_at="2026-09-01T08:00:00-04:00", source_url="https://example.com")
    resolved, _unresolved = resolve_lineup_teams([lineup], _salary_players(), empty_depth_chart)
    assert resolved[0].players[0].team == "CHI"
    assert resolved[0].players[0].depth_slot is None
