from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_logs.game_logs import GameLogRow
from backend.services.game_logs.game_logs_engine import (
    build_game_log_rows,
    build_game_options,
    build_team_stat_summary,
    tier_for_stat_value,
)
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


def test_build_game_options_filters_to_contest_teams_when_provided():
    # SCHEDULE_CSV has games TEN@CLE (wk13), TEN@SF (wk14), TEN@KC (wk15)
    # -- if only KC/TEN are in this week's Contest slate, week 15's game
    # (both teams in the salary file) shows but games from other weeks
    # aren't in games_for_week(week=15) anyway, so build a schedule with
    # two SIMULTANEOUS week-15 games to actually exercise the filter.
    schedule_rows = parse_schedule_csv(
        "Team,Week,Opponent,GameLocation\n"
        "TEN,15,KC,Away\n"
        "KC,15,TEN,Home\n"
        "SF,15,DAL,Away\n"
        "DAL,15,SF,Home\n"
    )
    options = build_game_options(schedule_rows, 15, contest_teams={"TEN", "KC"})
    assert [o.teams for o in options] == [["KC", "TEN"]]


def test_build_game_options_drops_game_with_only_one_team_in_contest():
    # A game where only one side is on the contest's slate isn't a real
    # playable matchup for that contest -- drop it entirely rather than
    # showing a one-sided "game."
    schedule_rows = parse_schedule_csv(
        "Team,Week,Opponent,GameLocation\nTEN,15,KC,Away\nKC,15,TEN,Home\n"
    )
    options = build_game_options(schedule_rows, 15, contest_teams={"TEN"})
    assert options == []


def test_build_game_options_contest_teams_none_keeps_every_game():
    # The default (None) -- backward-compatible, no filtering at all.
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    assert build_game_options(schedule_rows, 15, contest_teams=None) == build_game_options(schedule_rows, 15)


def test_build_game_log_rows_uses_latest_week_at_or_before_requested_as_reference():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 13, 4600, 6.34, 6.34, 0.0),
        _row("Cam Ward", "QB", "TEN", 14, 4800, 12.08, 4.08, 8.0),
    ]
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    # Requesting week 15 (not yet added to the tracker) should fall back to
    # week 14 as the reference for ROSTER purposes -- but the history
    # window itself is anchored on the raw requested week (15), not
    # reference_week, so week 14's own row DOES still appear as history
    # (it's strictly before week 15) -- see build_game_log_rows' own
    # docstring for why this decoupling matters (week 15's own "Add Week
    # Players" shouldn't gate seeing week 14's already-complete results).
    rows, reference_week = build_game_log_rows(tracker_rows, schedule_rows, {}, week=15, lookback_weeks=6)
    assert reference_week == 14
    assert sorted(r.week for r in rows) == [13, 14]


def test_build_game_log_rows_history_window_independent_of_reference_week():
    # The exact scenario the decoupling fixes: it's week 2, but "Add Week 2
    # Players" hasn't run yet (tracker's latest week is still 1) -- week 1's
    # own complete history should still show up rather than the tab coming
    # back empty just because reference_week (1) hasn't caught up to the
    # requested week (2) yet.
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 1, 4500, 10.0, 5.0, 5.0),
    ]
    rows, reference_week = build_game_log_rows(tracker_rows, [], {}, week=2, lookback_weeks=6)
    assert reference_week == 1
    assert sorted(r.week for r in rows) == [1]


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
    stat_lines = {
        "RB": {
            ("Tony Pollard", 13): {
                "rush_att": 12,
                "rush_yards": 60,
                "rush_td": 1,
                "targets": 2,
                "receptions": 1,
                "receiving_yards": 3,
                "rec_td": 0,
            }
        }
    }
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.rush_att == 12
    assert row.rush_yards == 60
    assert row.rush_td == 1
    assert row.targets == 2
    assert row.receptions == 1
    assert row.receiving_yards == 3
    assert row.rec_td == 0
    assert row.touches == 13  # 12 rush_att + 1 reception


def test_build_game_log_rows_qb_has_no_receiving_stats():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 13, 4600, 6.34, 6.34, 0.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
    ]
    # QB's FantasyData file has no RECEIVING_* columns at all -- so its
    # stat line here simply has no "targets"/"receptions"/"receiving_yards"/
    # "rec_td" keys, same shape load_weekly_stat_lines would produce for a
    # QB file. rush_td IS present -- a QB's file carries RUSHING_TD too.
    stat_lines = {"QB": {("Cam Ward", 13): {"rush_att": 5, "rush_yards": 29, "rush_td": 1}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.rush_att == 5
    assert row.rush_yards == 29
    assert row.rush_td == 1
    assert row.targets is None
    assert row.receptions is None
    assert row.receiving_yards is None
    assert row.rec_td is None
    assert row.touches == 5  # rush_att + 0 receptions (missing key defaults to 0)


def test_build_game_log_rows_qb_includes_passing_line():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 13, 4600, 29.4, 15.4, 14.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
    ]
    stat_lines = {
        "QB": {
            ("Cam Ward", 13): {
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
                "team": "TEN",
            }
        }
    }
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
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


def test_build_game_log_rows_non_qb_has_no_passing_line():
    tracker_rows = [
        _row("Tony Pollard", "RB", "TEN", 13, 4900, 6.3, 6.3, 0.0),
        _row("Tony Pollard", "RB", "TEN", 15, 4900, 0.0, 0.0, 0.0),
    ]
    # RB's own stat line has no PASSING_*/INT/SCK/RATING keys at all --
    # same shape load_weekly_stat_lines produces for a non-QB file.
    stat_lines = {"RB": {("Tony Pollard", 13): {"rush_att": 12, "rush_yards": 60}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.pass_cmp is None
    assert row.pass_att is None
    assert row.pass_cmp_pct is None
    assert row.pass_yds is None
    assert row.pass_avg is None
    assert row.pass_td is None
    assert row.pass_int is None
    assert row.pass_sck is None
    assert row.pass_rtg is None


def test_build_game_log_rows_dst_includes_sacks_from_its_own_stat_file():
    tracker_rows = [
        _row("Chargers", "DST", "LAC", 13, 2500, 17.0, 17.0, 0.0, roster_position="DST"),
        _row("Chargers", "DST", "LAC", 15, 2500, 0.0, 0.0, 0.0, roster_position="DST"),
    ]
    stat_lines = {"DST": {("Chargers", 13): {"sacks": 4, "team": "LAC"}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.sacks == 4


def test_build_game_log_rows_non_dst_has_no_sacks():
    tracker_rows = [
        _row("Tony Pollard", "RB", "TEN", 13, 4900, 6.3, 6.3, 0.0),
        _row("Tony Pollard", "RB", "TEN", 15, 4900, 0.0, 0.0, 0.0),
    ]
    stat_lines = {"RB": {("Tony Pollard", 13): {"rush_att": 12, "rush_yards": 60}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    assert rows[0].sacks is None


def test_build_game_log_rows_filters_roster_to_contest_teams_when_provided():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 14, 5000, 20.0, 5.0, 15.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
        _row("Some WR", "WR", "SF", 14, 5000, 12.0, 8.0, 4.0),
        _row("Some WR", "WR", "SF", 15, 4800, 0.0, 0.0, 0.0),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6, contest_teams={"TEN", "KC"})
    # SF isn't in the contest's slate this week -- "Some WR" is excluded
    # even though their tracker row and history are otherwise identical
    # in shape to Cam Ward's.
    assert [r.name for r in rows] == ["Cam Ward"]


def test_build_game_log_rows_contest_teams_none_keeps_every_team():
    tracker_rows = [
        _row("Cam Ward", "QB", "TEN", 14, 5000, 20.0, 5.0, 15.0),
        _row("Cam Ward", "QB", "TEN", 15, 4800, 0.0, 0.0, 0.0),
        _row("Some WR", "WR", "SF", 14, 5000, 12.0, 8.0, 4.0),
        _row("Some WR", "WR", "SF", 15, 4800, 0.0, 0.0, 0.0),
    ]
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    assert sorted(r.name for r in rows) == ["Cam Ward", "Some WR"]


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


# -- target_share_pct / touch_share_pct / opp_share_pct -----------------------
#
# TGTSHARE/TOUCHSHARE/OPPSHARE are precomputed once by "Calc Week Points &
# Fantasy Data" (backend/services/shared/usage_shares.py) and stored as
# TGT_SHARE/TOUCH_SHARE/OPP_SHARE columns on the FantasyData files themselves -- see
# weekly_stats_loader.load_weekly_stat_lines. build_game_log_rows just
# reads them straight off the stat line, same as every other usage stat --
# it does no team-aggregate computation of its own (that's covered by
# test_usage_shares.py instead).


def test_build_game_log_rows_reads_precomputed_shares_from_stat_line():
    tracker_rows = [
        _row("Tony Pollard", "RB", "TEN", 13, 4900, 20.0, 14.0, 6.0),
        _row("Tony Pollard", "RB", "TEN", 15, 4900, 0.0, 0.0, 0.0),
    ]
    stat_lines = {
        "RB": {
            ("Tony Pollard", 13): {
                "rush_att": 12,
                "rush_yards": 60,
                "targets": 2,
                "receptions": 1,
                "receiving_yards": 3,
                "team": "TEN",
                "target_share_pct": 28.6,
                "touch_share_pct": 65.0,
                "opp_share_pct": 50.0,
            }
        },
    }
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.target_share_pct == 28.6
    assert row.touch_share_pct == 65.0
    assert row.opp_share_pct == 50.0


def test_build_game_log_rows_shares_none_when_stat_line_has_no_share_keys():
    tracker_rows = [
        _row("Tony Pollard", "RB", "TEN", 13, 4900, 6.3, 6.3, 0.0),
        _row("Tony Pollard", "RB", "TEN", 15, 4900, 0.0, 0.0, 0.0),
    ]
    # No FantasyData file at all -- stat_lines_by_position is empty, so
    # there's no stat_line to read target_share_pct/touch_share_pct/
    # opp_share_pct from.
    rows, _ = build_game_log_rows(tracker_rows, [], {}, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.target_share_pct is None
    assert row.touch_share_pct is None
    assert row.opp_share_pct is None


def test_build_game_log_rows_resolves_name_via_alias_when_no_native_match():
    # Tracker spells the player "Brian Robinson Jr." but the FantasyData
    # stat file (independently scraped) spells him "Brian Robinson" -- a
    # direct (name, week) lookup misses, so this should fall back through
    # name_aliases (Settings' Name Aliases panel) to find the stat line.
    tracker_rows = [
        _row("Brian Robinson Jr.", "RB", "ATL", 1, 5500, 12.0, 6.0, 6.0),
        _row("Brian Robinson Jr.", "RB", "ATL", 2, 5500, 0.0, 0.0, 0.0),
    ]
    stat_lines = {
        "RB": {
            ("Brian Robinson", 1): {"rush_att": 9, "rush_yards": 31, "team": "ATL"},
        }
    }
    name_aliases = {"Brian Robinson Jr.": "Brian Robinson"}
    rows, _ = build_game_log_rows(
        tracker_rows, [], stat_lines, week=2, lookback_weeks=6, name_aliases=name_aliases
    )
    row = rows[0]
    assert row.rush_att == 9
    assert row.rush_yards == 31


def test_build_game_log_rows_native_name_tried_before_alias():
    # If the tracker's own spelling already matches the stat file natively,
    # the alias (which would point somewhere else) must not be applied --
    # name_lookup_candidates tries the raw name first.
    tracker_rows = [
        _row("Brian Robinson", "RB", "ATL", 1, 5500, 12.0, 6.0, 6.0),
        _row("Brian Robinson", "RB", "ATL", 2, 5500, 0.0, 0.0, 0.0),
    ]
    stat_lines = {
        "RB": {
            ("Brian Robinson", 1): {"rush_att": 9, "rush_yards": 31, "team": "ATL"},
        }
    }
    name_aliases = {"Brian Robinson Jr.": "Brian Robinson"}
    rows, _ = build_game_log_rows(
        tracker_rows, [], stat_lines, week=2, lookback_weeks=6, name_aliases=name_aliases
    )
    row = rows[0]
    assert row.rush_att == 9


def test_build_game_log_rows_no_match_still_none_when_alias_missing():
    # Without a matching alias entry, a genuine spelling mismatch simply
    # looks like "no stats recorded" -- same as any other missing stat
    # line, not an error.
    tracker_rows = [
        _row("Brian Robinson Jr.", "RB", "ATL", 1, 5500, 12.0, 6.0, 6.0),
        _row("Brian Robinson Jr.", "RB", "ATL", 2, 5500, 0.0, 0.0, 0.0),
    ]
    stat_lines = {"RB": {("Brian Robinson", 1): {"rush_att": 9, "rush_yards": 31, "team": "ATL"}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=2, lookback_weeks=6)
    row = rows[0]
    assert row.rush_att is None
    assert row.rush_yards is None


def test_build_game_log_rows_shares_none_when_calc_week_points_not_run_yet():
    # The stat file exists and has this player's raw usage numbers, but
    # "Calc Week Points & Fantasy Data" hasn't been run for this week yet
    # -- no TGT_SHARE/TOUCH_SHARE/OPP_SHARE columns in the file yet, so
    # load_weekly_stat_lines never puts target_share_pct/touch_share_pct/
    # opp_share_pct in the stat line at all.
    tracker_rows = [
        _row("Tony Pollard", "RB", "TEN", 13, 4900, 6.3, 6.3, 0.0),
        _row("Tony Pollard", "RB", "TEN", 15, 4900, 0.0, 0.0, 0.0),
    ]
    stat_lines = {"RB": {("Tony Pollard", 13): {"rush_att": 12, "rush_yards": 60, "team": "TEN"}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=15, lookback_weeks=6)
    row = rows[0]
    assert row.target_share_pct is None
    assert row.touch_share_pct is None
    assert row.opp_share_pct is None


def _log_row(
    name,
    position,
    team,
    week,
    receptions=None,
    receiving_yards=None,
    rec_td=None,
    rush_att=None,
    rush_yards=None,
    rush_td=None,
    pass_att=None,
    pass_yds=None,
    pass_td=None,
):
    # Minimal GameLogRow for build_player_stat_summary tests -- only the
    # fields that function actually reads (name/position + the 9 counting
    # stats) are varied; everything else gets an arbitrary-but-valid value
    # since the schema requires every field.
    return GameLogRow(
        week=week,
        name=name,
        position=position,
        team=team,
        salary=5000,
        opponent=None,
        game_location=None,
        multiplier=None,
        fpts=0.0,
        non_td_fpts=0.0,
        non_td_fpts_pct=None,
        td_fpts=0.0,
        td_fpts_pct=None,
        touches=None,
        targets=None,
        receptions=receptions,
        receiving_yards=receiving_yards,
        rec_td=rec_td,
        rush_att=rush_att,
        rush_yards=rush_yards,
        rush_td=rush_td,
        target_share_pct=None,
        touch_share_pct=None,
        opp_share_pct=None,
        pass_cmp=None,
        pass_att=pass_att,
        pass_cmp_pct=None,
        pass_yds=pass_yds,
        pass_avg=None,
        pass_td=pass_td,
        pass_int=None,
        pass_sck=None,
        pass_rtg=None,
        pass_att_tier=tier_for_stat_value("pass_att", pass_att),
        pass_yds_tier=tier_for_stat_value("pass_yds", pass_yds),
        sacks=None,
    )


def test_build_team_stat_summary_sums_players_per_week_then_averages_across_weeks():
    # Week 1: RB1 60 + RB2 20 = 80 team rush yards. Week 2: RB1 40 + RB2 60
    # = 100. Average/median are over the two WEEK TOTALS (80, 100), not
    # over the 4 individual player-week values.
    rows = [
        _log_row("RB1", "RB", "ATL", 1, rush_att=10, rush_yards=60),
        _log_row("RB2", "RB", "ATL", 1, rush_att=5, rush_yards=20),
        _log_row("RB1", "RB", "ATL", 2, rush_att=8, rush_yards=40),
        _log_row("RB2", "RB", "ATL", 2, rush_att=12, rush_yards=60),
    ]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    assert len(summary) == 1
    row = summary[0]
    assert row.team == "ATL"
    assert row.games == 2
    assert row.rush_yards.average == 90.0  # (80 + 100) / 2
    assert row.rush_yards.median == 90.0
    assert row.rush_att.average == 17.5  # (15 + 20) / 2


def test_build_team_stat_summary_median_of_even_count_averages_middle_two():
    rows = [
        _log_row("RB1", "RB", "LAR", 1, rush_yards=40),
        _log_row("RB1", "RB", "LAR", 2, rush_yards=60),
        _log_row("RB1", "RB", "LAR", 3, rush_yards=80),
        _log_row("RB1", "RB", "LAR", 4, rush_yards=100),
    ]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    row = summary[0]
    assert row.rush_yards.average == 70.0
    assert row.rush_yards.median == 70.0  # (60 + 80) / 2


def test_build_team_stat_summary_none_stat_excluded_not_treated_as_zero():
    # A non-QB row's pass_yds is always None -- it must not drag the team's
    # own Pass Yds average down as if that player's "share" were a real 0.
    rows = [
        _log_row("QB1", "QB", "PHI", 1, pass_yds=300),
        _log_row("RB1", "RB", "PHI", 1, pass_yds=None, rush_yards=40),
        _log_row("QB1", "QB", "PHI", 2, pass_yds=250),
    ]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    row = summary[0]
    assert row.pass_yds.average == 275.0  # (300 + 250) / 2, RB1's None ignored
    assert row.rush_yards.average == 40.0


def test_build_team_stat_summary_week_with_no_value_for_a_stat_excluded_from_that_stats_average():
    # Week 2 has no QB row at all (e.g. name-match miss) -- Pass Yds has no
    # team total for week 2, so it's left out of Pass Yds' own
    # average/median entirely, while `games` (which counts weeks with ANY
    # row) still reflects both weeks.
    rows = [
        _log_row("QB1", "QB", "DAL", 1, pass_yds=300),
        _log_row("RB1", "RB", "DAL", 1, rush_yards=50),
        _log_row("RB1", "RB", "DAL", 2, rush_yards=70),
    ]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    row = summary[0]
    assert row.games == 2
    assert row.pass_yds.average == 300.0
    assert row.rush_yards.average == 60.0  # (50 + 70) / 2


def test_build_team_stat_summary_all_none_stat_stays_none():
    rows = [_log_row("K1", "QB", "BAL", 1, pass_yds=None)]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    row = summary[0]
    assert row.pass_yds.average is None
    assert row.pass_yds.median is None


def test_build_team_stat_summary_groups_separately_by_team():
    rows = [
        _log_row("Josh Jacobs", "RB", "GB", 1, rush_yards=80),
        _log_row("Josh Jacobs", "RB", "GB", 2, rush_yards=120),
        _log_row("Zamir White", "RB", "LV", 1, rush_yards=10),
    ]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    assert len(summary) == 2
    gb_row = next(r for r in summary if r.team == "GB")
    lv_row = next(r for r in summary if r.team == "LV")
    assert gb_row.games == 2
    assert gb_row.rush_yards.average == 100.0
    assert lv_row.games == 1
    assert lv_row.rush_yards.average == 10.0


def test_build_team_stat_summary_get_team_uses_against_team_style_callable():
    # Mirrors how game_logs_against's own endpoint calls this with
    # `lambda r: r.against_team` instead of `lambda r: r.team` -- any
    # callable deriving the grouping key works, not just .team itself.
    rows = [_log_row("Saquon Barkley", "RB", "NYG", 1, rush_yards=90)]
    summary = build_team_stat_summary(rows, lambda r: f"vs-{r.team}")
    assert summary[0].team == "vs-NYG"


def test_build_team_stat_summary_sorted_by_team():
    rows = [
        _log_row("P1", "WR", "SEA", 1, rush_yards=50),
        _log_row("P2", "RB", "ATL", 1, rush_yards=50),
    ]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    assert [r.team for r in summary] == ["ATL", "SEA"]


def test_build_team_stat_summary_no_longer_has_receptions_or_receiving_yards_fields():
    # Dropped from TeamStatSummaryRow at the person's own request -- still
    # present on every per-week GameLogRow, just not summarized here.
    row = build_team_stat_summary([_log_row("P1", "WR", "SEA", 1, receiving_yards=50, receptions=3)], lambda r: r.team)[0]
    assert not hasattr(row, "receptions")
    assert not hasattr(row, "receiving_yards")


def test_tier_for_stat_value_thresholds():
    assert tier_for_stat_value("pass_yds", 175) == "low"
    assert tier_for_stat_value("pass_yds", 176) is None
    assert tier_for_stat_value("pass_yds", 260) is None
    assert tier_for_stat_value("pass_yds", 261) == "high"
    assert tier_for_stat_value("pass_att", 28) == "low"
    assert tier_for_stat_value("pass_att", 38) == "high"
    assert tier_for_stat_value("rush_yards", 85) == "low"
    assert tier_for_stat_value("rush_yards", 141) == "high"
    assert tier_for_stat_value("rush_att", 21) == "low"
    assert tier_for_stat_value("rush_att", 30) == "high"
    assert tier_for_stat_value("pass_yds", None) is None
    # No thresholds defined for TD stats.
    assert tier_for_stat_value("pass_td", 5) is None


def test_build_team_stat_summary_average_and_median_tiers_computed():
    rows = [
        _log_row("QB1", "QB", "DAL", 1, pass_yds=150, pass_att=25),
        _log_row("QB1", "QB", "DAL", 2, pass_yds=170, pass_att=26),
    ]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    row = summary[0]
    assert row.pass_yds.average == 160.0
    assert row.pass_yds.average_tier == "low"
    assert row.pass_yds.median_tier == "low"
    assert row.pass_att.average_tier == "low"


def test_build_team_stat_summary_tier_none_for_td_stats():
    rows = [_log_row("QB1", "QB", "DAL", 1, pass_td=3)]
    summary = build_team_stat_summary(rows, lambda r: r.team)
    row = summary[0]
    assert row.pass_td.average_tier is None
    assert row.pass_td.median_tier is None


def test_build_game_log_rows_pass_tier_fields_computed():
    tracker_rows = [_row("QB1", "QB", "DAL", 15, 7000, 20.0, 14.0, 6.0)]
    stat_lines = {"QB": {("QB1", 15): {"pass_yds": 150, "pass_att": 25}}}
    rows, _ = build_game_log_rows(tracker_rows, [], stat_lines, week=16, lookback_weeks=6)
    row = rows[0]
    assert row.pass_yds_tier == "low"
    assert row.pass_att_tier == "low"
