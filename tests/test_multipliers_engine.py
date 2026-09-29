from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.services.multipliers.multipliers_engine import build_multiplier_rows
from backend.services.schedule.schedule_loader import parse_schedule_csv

SCHEDULE_CSV = (
    "Team,Week,Opponent,GameLocation\n"
    "TEN,13,CLE,Away\n"
    "CLE,13,TEN,Home\n"
    "TEN,14,SF,Home\n"
    "SF,14,TEN,Away\n"
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


def test_build_multiplier_rows_base_week_is_always_current_week_minus_one():
    tracker_rows = [_row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4)]
    _rows, base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    assert base_week == 13


def test_build_multiplier_rows_uses_base_weeks_own_line():
    tracker_rows = [_row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4)]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    assert len(rows) == 1
    row = rows[0]
    assert row.week == 13
    assert row.salary == 7700
    assert row.fpts == 30.8
    assert row.multiplier == 30.8 / (7700 / 1000)


def test_build_multiplier_rows_base_non_td_multiplier():
    tracker_rows = [_row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4)]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    assert rows[0].non_td_multiplier == 15.4 / (7700 / 1000)


def test_build_multiplier_rows_skips_player_with_no_base_week_row():
    # Only has a week 12 row -- never appeared in week 13's tracker at all
    # (released/inactive that week), so there's no base-week line to show.
    tracker_rows = [_row("Bench Guy", "RB", "TEN", 12, 4500, 8.0, 8.0, 0.0)]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    assert rows == []


def test_build_multiplier_rows_excludes_zero_fpts_for_non_dst():
    tracker_rows = [_row("Bust", "WR", "TEN", 13, 5000, 0.0, 0.0, 0.0)]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    assert rows == []


def test_build_multiplier_rows_keeps_zero_fpts_dst_rows():
    tracker_rows = [_row("Titans DST", "DST", "TEN", 13, 2400, 0.0, 0.0, 0.0, roster_position="DST")]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    assert [r.name for r in rows] == ["Titans DST"]
    assert rows[0].fpts == 0.0


def test_build_multiplier_rows_excludes_unsupported_positions():
    tracker_rows = [_row("Some Kicker", "K", "TEN", 13, 4000, 8.0, 8.0, 0.0, roster_position="K")]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    assert rows == []


def test_build_multiplier_rows_opponent_and_game_location_from_schedule():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [_row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4)]
    rows, _base_week = build_multiplier_rows(tracker_rows, schedule_rows, week=14, trailing_weeks=5)
    assert rows[0].opponent == "CLE"
    assert rows[0].game_location == "Away"


def test_build_multiplier_rows_opponent_none_when_schedule_missing():
    tracker_rows = [_row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4)]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    assert rows[0].opponent is None
    assert rows[0].game_location is None


def test_build_multiplier_rows_non_td_and_td_pct_math():
    tracker_rows = [_row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4)]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    row = rows[0]
    assert row.non_td_fpts_pct == 50.0
    assert row.td_fpts_pct == 50.0


# -- contest_teams scoping ----------------------------------------------


def test_build_multiplier_rows_filters_by_contest_teams():
    tracker_rows = [
        _row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4),
        _row("Other QB", "QB", "SF", 13, 6000, 20.0, 10.0, 10.0),
    ]
    rows, _base_week = build_multiplier_rows(
        tracker_rows, [], week=14, trailing_weeks=5, contest_teams={"TEN"}
    )
    assert [r.name for r in rows] == ["Josh Allen"]


def test_build_multiplier_rows_none_contest_teams_keeps_everyone():
    tracker_rows = [
        _row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4),
        _row("Other QB", "QB", "SF", 13, 6000, 20.0, 10.0, 10.0),
    ]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5, contest_teams=None)
    assert {r.name for r in rows} == {"Josh Allen", "Other QB"}


# -- trailing multiplier columns -----------------------------------------


def test_build_multiplier_rows_trailing_columns_cover_the_requested_count_in_order():
    tracker_rows = [_row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4)]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    trailing = rows[0].trailing
    assert [t.week for t in trailing] == [12, 11, 10, 9, 8]


def test_build_multiplier_rows_trailing_multiplier_computed_when_row_exists():
    tracker_rows = [
        _row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4),
        _row("Josh Allen", "QB", "TEN", 12, 7500, 22.5, 11.25, 11.25),
    ]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    trailing_by_week = {t.week: t.multiplier for t in rows[0].trailing}
    assert trailing_by_week[12] == 22.5 / (7500 / 1000)
    assert trailing_by_week[11] is None
    assert trailing_by_week[10] is None
    assert trailing_by_week[9] is None
    assert trailing_by_week[8] is None


def test_build_multiplier_rows_trailing_non_td_multiplier_computed_when_row_exists():
    tracker_rows = [
        _row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4),
        _row("Josh Allen", "QB", "TEN", 12, 7500, 22.5, 11.25, 11.25),
    ]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    trailing_by_week = {t.week: t.non_td_multiplier for t in rows[0].trailing}
    assert trailing_by_week[12] == 11.25 / (7500 / 1000)
    assert trailing_by_week[11] is None


def test_build_multiplier_rows_trailing_td_fpts_present_when_row_exists():
    tracker_rows = [
        _row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4),
        _row("Josh Allen", "QB", "TEN", 12, 7500, 22.5, 11.25, 11.25),
    ]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    td_fpts_by_week = {t.week: t.td_fpts for t in rows[0].trailing}
    assert td_fpts_by_week[12] == 11.25
    assert td_fpts_by_week[11] is None


def test_build_multiplier_rows_trailing_multiplier_none_when_salary_zero():
    tracker_rows = [
        _row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4),
        _row("Josh Allen", "QB", "TEN", 12, 0, 22.5, 11.25, 11.25),
    ]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    trailing_by_week = {t.week: t.multiplier for t in rows[0].trailing}
    assert trailing_by_week[12] is None
    non_td_by_week = {t.week: t.non_td_multiplier for t in rows[0].trailing}
    assert non_td_by_week[12] is None


def test_build_multiplier_rows_respects_configurable_trailing_weeks_count():
    tracker_rows = [_row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4)]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=2)
    assert [t.week for t in rows[0].trailing] == [12, 11]


def test_build_multiplier_rows_trailing_ignores_zero_fpts_filter():
    # The 0-FPTS-hides-the-row rule only applies to whether the BASE
    # week's own row shows at all -- a trailing week's own multiplier is
    # still computed even if that week's FPTS happened to be 0 (still
    # real, meaningful history, not a "didn't play" case to hide).
    tracker_rows = [
        _row("Josh Allen", "QB", "TEN", 13, 7700, 30.8, 15.4, 15.4),
        _row("Josh Allen", "QB", "TEN", 12, 7500, 0.0, 0.0, 0.0),
    ]
    rows, _base_week = build_multiplier_rows(tracker_rows, [], week=14, trailing_weeks=5)
    trailing_by_week = {t.week: t.multiplier for t in rows[0].trailing}
    assert trailing_by_week[12] == 0.0
