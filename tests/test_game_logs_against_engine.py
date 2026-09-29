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


# -- touches / targets / receptions / receiving_yards / rush_att / rush_yards --


def test_build_game_logs_against_rows_usage_stats_for_rb_include_touches():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Brock Purdy", "RB", "SF", 15, 5800, 22.0, 10.0, 12.0),
    ]
    stat_lines = {
        "RB": {
            ("Brock Purdy", 15): {
                "rush_att": 12,
                "rush_yards": 60,
                "rush_td": 1,
                "targets": 2,
                "receptions": 1,
                "receiving_yards": 3,
                "rec_td": 0,
                "team": "SF",
            }
        }
    }
    rows = build_game_logs_against_rows(
        tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6, stat_lines_by_position=stat_lines
    )
    row = rows[0]
    assert row.rush_att == 12
    assert row.rush_yards == 60
    assert row.rush_td == 1
    assert row.targets == 2
    assert row.receptions == 1
    assert row.receiving_yards == 3
    assert row.rec_td == 0
    assert row.touches == 13  # 12 rush_att + 1 reception


def test_build_game_logs_against_rows_usage_stats_none_for_qb_without_receiving_columns():
    # QB's own FantasyData file has no targets/receptions/receiving_yards
    # column at all -- None (not 0), same convention as Game Logs' own
    # build_game_log_rows.
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 14.0, 8.0, 6.0),
    ]
    stat_lines = {"QB": {("Deshaun Watson", 13): {"rush_att": 5, "rush_yards": 29, "rush_td": 1, "team": "CLE"}}}
    rows = build_game_logs_against_rows(
        tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6, stat_lines_by_position=stat_lines
    )
    row = rows[0]
    assert row.rush_att == 5
    assert row.rush_yards == 29
    assert row.rush_td == 1
    assert row.targets is None
    assert row.receptions is None
    assert row.receiving_yards is None
    assert row.rec_td is None
    assert row.touches == 5  # rush_att + 0 receptions (missing key defaults to 0)


def test_build_game_logs_against_rows_usage_stats_none_without_stat_lines():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 14.0, 8.0, 6.0),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    row = rows[0]
    assert row.touches is None
    assert row.targets is None
    assert row.receptions is None
    assert row.receiving_yards is None
    assert row.rec_td is None
    assert row.rush_att is None
    assert row.rush_yards is None
    assert row.rush_td is None


# -- target_share_pct / touch_share_pct / opp_share_pct / passing line --------


def test_build_game_logs_against_rows_defaults_shares_and_passing_to_none_without_stat_lines():
    # No stat_lines_by_position passed at all (the default) -- every
    # existing caller/test above relies on this staying a safe no-op.
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 14.0, 8.0, 6.0),
    ]
    rows = build_game_logs_against_rows(tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6)
    row = rows[0]
    assert row.target_share_pct is None
    assert row.touch_share_pct is None
    assert row.opp_share_pct is None
    assert row.pass_cmp is None
    assert row.pass_rtg is None


def test_build_game_logs_against_rows_reads_precomputed_shares_from_stat_line():
    # TGTSHARE/TOUCHSHARE/OPPSHARE are precomputed once by "Calc Week
    # Points & Fantasy Data" (backend/services/shared/usage_shares.py) and
    # stored as TGT_SHARE/TOUCH_SHARE/OPP_SHARE columns on the FantasyData files -- this
    # just reads them straight off the stat line, same as Game Logs' own
    # passthrough (see test_usage_shares.py for the actual team-aggregate
    # computation).
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 14.0, 8.0, 6.0),
    ]
    stat_lines = {
        "QB": {
            ("Deshaun Watson", 13): {
                "rush_att": 3,
                "rush_yards": 15,
                "team": "CLE",
                "target_share_pct": None,
                "touch_share_pct": 50.0,
                "opp_share_pct": 40.0,
            }
        },
    }
    rows = build_game_logs_against_rows(
        tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6, stat_lines_by_position=stat_lines
    )
    row = rows[0]
    assert row.touch_share_pct == 50.0
    assert row.target_share_pct is None
    assert row.opp_share_pct == 40.0
    assert row.rush_att == 3
    assert row.rush_yards == 15


def test_build_game_logs_against_rows_qb_includes_passing_line():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Deshaun Watson", "QB", "CLE", 13, 5200, 29.4, 15.4, 14.0),
    ]
    stat_lines = {
        "QB": {
            ("Deshaun Watson", 13): {
                "rush_att": 6,
                "rush_yards": 70,
                "pass_cmp": 14,
                "pass_att": 19,
                "pass_cmp_pct": 73.7,
                "pass_yds": 209,
                "pass_avg": 11.0,
                "pass_td": 2,
                "pass_int": 0,
                "pass_sck": 2,
                "pass_rtg": 144.4,
                "team": "CLE",
            }
        }
    }
    rows = build_game_logs_against_rows(
        tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6, stat_lines_by_position=stat_lines
    )
    row = rows[0]
    assert row.pass_cmp == 14
    assert row.pass_att == 19
    assert row.pass_cmp_pct == 73.7
    assert row.pass_yds == 209
    assert row.pass_avg == 11.0
    assert row.pass_td == 2
    assert row.pass_int == 0
    assert row.pass_sck == 2
    assert row.pass_rtg == 144.4


def test_build_game_logs_against_rows_dst_includes_sacks():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Browns", "DST", "CLE", 13, 2400, 12.0, 12.0, 0.0, roster_position="DST"),
    ]
    stat_lines = {"DST": {("Browns", 13): {"sacks": 3, "team": "CLE"}}}
    rows = build_game_logs_against_rows(
        tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6, stat_lines_by_position=stat_lines
    )
    row = rows[0]
    assert row.sacks == 3


def test_build_game_logs_against_rows_resolves_name_via_alias_when_no_native_match():
    # Same cross-source spelling drift as Game Logs' own alias test --
    # tracker "Brian Robinson Jr." vs. stat file "Brian Robinson".
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Brian Robinson Jr.", "RB", "CLE", 13, 5500, 12.0, 6.0, 6.0),
    ]
    stat_lines = {
        "RB": {
            ("Brian Robinson", 13): {
                "rush_att": 9,
                "rush_yards": 31,
                "team": "CLE",
                "touch_share_pct": 45.0,
                "opp_share_pct": 50.0,
            }
        }
    }
    name_aliases = {"Brian Robinson Jr.": "Brian Robinson"}
    rows = build_game_logs_against_rows(
        tracker_rows,
        schedule_rows,
        team="TEN",
        week=16,
        lookback_weeks=6,
        stat_lines_by_position=stat_lines,
        name_aliases=name_aliases,
    )
    row = rows[0]
    assert row.touch_share_pct == 45.0
    assert row.opp_share_pct == 50.0


def test_build_game_logs_against_rows_no_match_still_none_when_alias_missing():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Brian Robinson Jr.", "RB", "CLE", 13, 5500, 12.0, 6.0, 6.0),
    ]
    stat_lines = {"RB": {("Brian Robinson", 13): {"rush_att": 9, "rush_yards": 31, "team": "CLE"}}}
    rows = build_game_logs_against_rows(
        tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6, stat_lines_by_position=stat_lines
    )
    row = rows[0]
    assert row.target_share_pct is None
    assert row.touch_share_pct is None
    assert row.opp_share_pct is None


def test_build_game_logs_against_rows_non_qb_has_no_passing_line():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    tracker_rows = [
        _row("Brock Purdy", "RB", "SF", 15, 5800, 22.0, 10.0, 12.0),
    ]
    stat_lines = {"RB": {("Brock Purdy", 15): {"rush_att": 10, "rush_yards": 50, "team": "SF"}}}
    rows = build_game_logs_against_rows(
        tracker_rows, schedule_rows, team="TEN", week=16, lookback_weeks=6, stat_lines_by_position=stat_lines
    )
    row = rows[0]
    assert row.pass_cmp is None
    assert row.pass_rtg is None
