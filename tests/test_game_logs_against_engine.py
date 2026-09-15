from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.services.game_logs.game_logs_against_engine import build_game_logs_against_rows
from backend.services.schedule.schedule_loader import parse_schedule_csv

# TEN's own schedule: played CLE (wk13), BYE (wk14), SF (wk15). CLE and SF
# also have their own rows for their game against TEN (the "other side" of
# the same matchup), which is what carries their own home/away designation
# for that week.
SCHEDULE_CSV = (
    "Team,Week,Opponent,GameLocation\n"
    "TEN,13,CLE,Away\n"
    "CLE,13,TEN,Home\n"
    "TEN,14,BYE,\n"
    "TEN,15,SF,Home\n"
    "SF,15,TEN,Away\n"
)


def _row(name, position, team, week, salary, fpts, non_td_fpts, td_fpts, roster_position=None, pct_drafted=0.0):
    return DkPlayerRow(
        name=name,
        position=position,
        roster_position=roster_position or f"{position}/FLEX",
        team=team,
        week=week,
        salary=salary,
        pct_drafted=pct_drafted,
        fpts=fpts,
        non_td_fpts=non_td_fpts,
        td_fpts=td_fpts,
    )


def test_build_game_logs_against_rows_pulls_opponents_own_box_score():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 14.0, 8.0, 6.0),
        _row("Brock Purdy", "QB", "SF", 15, 5800, 22.0, 10.0, 12.0),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    # TEN played CLE in wk13 and SF in wk15 (wk14 was a bye, contributes
    # nothing) -- each opponent's own tracker row for that week shows.
    assert [(r.week, r.name) for r in rows] == [(15, "Brock Purdy"), (13, "Deshaun Watson")]
    assert all(r.against_team == "TEN" for r in rows)


def test_build_game_logs_against_rows_skips_bye_week():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    rows = build_game_logs_against_rows([], schedule_rows, team="TEN", week=16, lookback_weeks=6)
    assert all(r.week != 14 for r in rows)


def test_build_game_logs_against_rows_respects_lookback_window():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 14.0, 8.0, 6.0),
        _row("Brock Purdy", "QB", "SF", 15, 5800, 22.0, 10.0, 12.0),
    ]
    # lookback_weeks=1 with week=16 means [15, 16) -- only wk15 (SF) is in
    # range, wk13 (CLE) falls outside it.
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=1)
    assert [r.name for r in rows] == ["Brock Purdy"]


def test_build_game_logs_against_rows_excludes_zero_fpts_for_non_dst():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 0.0, 0.0, 0.0),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    assert rows == []


def test_build_game_logs_against_rows_keeps_zero_fpts_dst_rows():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Browns DST", "DST", "CLE", 13, 2400, 0.0, 0.0, 0.0, roster_position="DST"),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    assert [r.name for r in rows] == ["Browns DST"]
    assert rows[0].fpts == 0.0


def test_build_game_logs_against_rows_excludes_unsupported_positions():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Some Kicker", "K", "CLE", 13, 4000, 8.0, 8.0, 0.0, roster_position="K"),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    assert rows == []


def test_build_game_logs_against_rows_game_location_from_opponents_own_schedule_row():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 14.0, 8.0, 6.0),
        _row("Brock Purdy", "QB", "SF", 15, 5800, 22.0, 10.0, 12.0),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    by_name = {r.name: r for r in rows}
    # CLE's own schedule row for wk13 says "Home" (CLE hosted TEN).
    assert by_name["Deshaun Watson"].game_location == "Home"
    # SF's own schedule row for wk15 says "Away" (SF played at TEN).
    assert by_name["Brock Purdy"].game_location == "Away"


def test_build_game_logs_against_rows_multiplier_and_pct_math():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5000, 20.0, 5.0, 15.0),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    row = rows[0]
    assert row.multiplier == 20.0 / (5000 / 1000)
    assert row.non_td_fpts_pct == 25.0
    assert row.td_fpts_pct == 75.0


def test_build_game_logs_against_rows_multiplier_none_when_salary_zero():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 0, 5.0, 5.0, 0.0),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    assert rows[0].multiplier is None


def test_build_game_logs_against_rows_empty_when_schedule_missing():
    rows = build_game_logs_against_rows([], [], team="TEN", week=16, lookback_weeks=6)
    assert rows == []
