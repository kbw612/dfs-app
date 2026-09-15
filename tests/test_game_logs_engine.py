from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.services.game_logs.game_logs_engine import build_game_log_rows, build_game_options
from backend.services.schedule.schedule_loader import parse_schedule_csv

SCHEDULE_CSV = (
    "Team,Week,Opponent,GameLocation\n"
    "TEN,13,CLE,Away\n"
    "CLE,13,TEN,Home\n"
    "TEN,14,SF,Home\n"
    "SF,14,TEN,Away\n"
    "TEN,15,KC,Away\n"
    "KC,15,TEN,Home\n"
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


def test_build_game_options_skips_bye_and_sorts_by_label():
    rows = parse_schedule_csv(SCHEDULE_CSV)
    options = build_game_options(rows, 14)
    assert len(options) == 1
    # TEN,14,SF,Home -- TEN is the home team, SF is away.
    assert options[0].label == "SF @ TEN"
    assert options[0].teams == ["SF", "TEN"]
    assert options[0].key == "SF-TEN"


def test_build_game_options_empty_when_schedule_missing():
    assert build_game_options([], 14) == []


def test_build_game_options_label_reflects_actual_home_team_not_alphabetical():
    # KC,15,TEN,Home -- KC is home, TEN is away, even though "KC" would
    # sort before "TEN" either way -- this specifically checks the label
    # isn't just alphabetically-sorted "vs" (KC happens to also be
    # alphabetically first here, so this asserts the actual away/home
    # value, not merely that it differs from sorted order).
    rows = parse_schedule_csv(SCHEDULE_CSV)
    options = build_game_options(rows, 15)
    assert options[0].label == "TEN @ KC"
    assert options[0].teams == ["KC", "TEN"]


def test_build_game_options_falls_back_to_vs_when_schedule_entry_missing():
    # A matchup that games_for_week can see (both rows present) but whose
    # first-sorted team's own row is then removed before build_game_options
    # runs -- simulates a malformed/partial schedule file rather than a
    # real reachable state through parse_schedule_csv alone.
    from backend.services.schedule.schedule_loader import ScheduleRow

    rows = [ScheduleRow(team="TEN", week=14, opponent="SF", game_location="Home")]
    options = build_game_options(rows, 14)
    assert options[0].label == "SF vs TEN"


def test_build_game_log_rows_uses_latest_week_at_or_before_requested_as_reference():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 13, 4600, 6.34, 6.34, 0.0),
        _row("Cam Ward", "QB", "TEN", 14, 4800, 12.08, 4.08, 8.0),
    ]
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    # Requesting week 15 (not yet added to the tracker) should fall back to
    # week 14 as the reference -- and week 14's own row should NOT appear
    # in the output (only weeks strictly before the reference week do).
    rows, reference_week = build_game_log_rows(tracker_rows, schedule_rows, {}, week=15, lookback_weeks=6)
    assert reference_week == 14
    assert [r.week for r in rows] == [13]


def test_build_game_log_rows_no_tracker_rows_returns_empty():
    rows, reference_week = build_game_log_rows([], [], {}, week=15, lookback_weeks=6)
    assert rows == []
    assert reference_week == 0


def test_build_game_log_rows_respects_lookback_window():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", w, 4500, 10.0, 5.0, 5.0) for w in (9, 10, 11, 12, 13, 14, 15)
    ]
    rows, reference_week = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=3)
    assert reference_week == 15
    # weeks in [15-3, 15) = [12, 15) = 12,13,14
    assert sorted(r.week for r in rows) == [12, 13, 14]


def test_build_game_log_rows_computes_multiplier_and_percentages():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 14, 5000, 20.0, 5.0, 15.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.week == 14
    assert row.multiplier == 20.0 / (5000 / 1000)
    assert row.non_td_fpts_pct == 25.0
    assert row.td_fpts_pct == 75.0


def test_build_game_log_rows_multiplier_none_when_salary_zero():
    # FPTS has to be nonzero here or the row itself would be dropped by
    # the 0-FPTS filter before multiplier is ever computed (see the
    # zero-FPTS-exclusion tests further down).
    tracker_rows = [
        _row("Nobody", "QB", "TEN", 14, 0, 5.0, 5.0, 0.0),
        _row("Nobody", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.multiplier is None  # salary is 0


def test_build_game_log_rows_pct_none_when_fpts_zero_for_dst():
    # A DST's 0.0-FPTS week still shows (see the zero-FPTS-exclusion tests
    # further down), so this is the one case where non_td_fpts_pct/
    # td_fpts_pct's own "None when FPTS is 0" branch is still reachable.
    tracker_rows = [
        _row("Titans DST", "DST", "TEN", 14, 2500, 0.0, 0.0, 0.0, roster_position="DST"),
        _row("Titans DST", "DST", "TEN", 15, 2500, 0.0, 0.0, 0.0, roster_position="DST"),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.non_td_fpts_pct is None
    assert row.td_fpts_pct is None


def test_build_game_log_rows_enriches_opponent_and_game_location():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 13, 4600, 6.34, 6.34, 0.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
    ]
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    rows, _ = build_game_log_rows(tracker_rows, schedule_rows, {}, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.opponent == "CLE"
    assert row.game_location == "Away"


def test_build_game_log_rows_opponent_none_when_schedule_missing():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 13, 4600, 6.34, 6.34, 0.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.opponent is None
    assert row.game_location is None


def test_build_game_log_rows_usage_stats_for_rb_include_touches():
    tracker_rows = [
        _row("Tony Pollard", "RB", "TEN", 13, 4900, 6.3, 6.3, 0.0),
        _row("Tony Pollard", "RB", "TEN", 15, 4900, 0.0, 0.0, 0.0),
    ]
    stat_lines = {"RB": {("Tony Pollard", 13): {"rush_att": 12, "rush_yards": 60, "targets": 2, "receptions": 1, "receiving_yards": 3}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.rush_att == 12
    assert row.rush_yards == 60
    assert row.targets == 2
    assert row.receptions == 1
    assert row.receiving_yards == 3
    assert row.touches == 13  # 12 rush_att + 1 reception


def test_build_game_log_rows_qb_has_no_receiving_stats():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 13, 4600, 6.34, 6.34, 0.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
    ]
    # QB's FantasyData file has no RECEIVING_* columns at all -- so its
    # stat line here simply has no "targets"/"receptions"/"receiving_yards"
    # keys, same shape load_weekly_stat_lines would produce for a QB file.
    stat_lines = {"QB": {("Cam Ward", 13): {"rush_att": 5, "rush_yards": 29}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.rush_att == 5
    assert row.rush_yards == 29
    assert row.targets is None
    assert row.receptions is None
    assert row.receiving_yards is None
    assert row.touches == 5  # rush_att + 0 receptions (missing key defaults to 0)


def test_build_game_log_rows_excludes_unsupported_positions_but_includes_dst():
    tracker_rows = [
        _row("Some Kicker", "K", "TEN", 13, 4000, 8.0, 8.0, 0.0, roster_position="K"),
        _row("Some Kicker", "K", "TEN", 15, 4000, 0.0, 0.0, 0.0, roster_position="K"),
        _row("Titans DST", "DST", "TEN", 13, 2500, 5.0, 5.0, 0.0, roster_position="DST"),
        _row("Titans DST", "DST", "TEN", 15, 2500, 0.0, 0.0, 0.0, roster_position="DST"),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    # K isn't a supported roster position at all -- only the DST row shows.
    assert [r.position for r in rows] == ["DST"]
    assert rows[0].week == 13
    assert rows[0].fpts == 5.0


def test_build_game_log_rows_excludes_zero_fpts_rows_for_non_dst():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 13, 4600, 0.0, 0.0, 0.0),
        _row("Cam Ward", "QB", "TEN", 14, 4800, 12.08, 4.08, 8.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    # Week 13's real 0.0 FPTS row is dropped -- only week 14's nonzero
    # performance shows (week 15 is the reference week and excluded
    # regardless, same as every other test above).
    assert [r.week for r in rows] == [14]


def test_build_game_log_rows_keeps_zero_fpts_dst_rows():
    tracker_rows = [
        _row("Titans DST", "DST", "TEN", 13, 2500, 0.0, 0.0, 0.0, roster_position="DST"),
        _row("Titans DST", "DST", "TEN", 15, 2500, 0.0, 0.0, 0.0, roster_position="DST"),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    # Unlike every other position, a DST's 0.0 FPTS week still shows --
    # a defense's own score is a real signal even when it's zero.
    assert [r.week for r in rows] == [13]
    assert rows[0].fpts == 0.0
