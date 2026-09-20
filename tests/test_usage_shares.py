from backend.services.shared.usage_shares import (
    compute_share_pcts,
    compute_touches,
    compute_usage_share_updates,
    team_usage_totals,
)


# -- team_usage_totals --------------------------------------------------------


def test_team_usage_totals_sums_across_all_positions():
    stat_lines_by_position = {
        "RB": {("Tony Pollard", 13): {"rush_att": 12, "receptions": 1, "targets": 2, "team": "TEN"}},
        "WR": {("Wide Receiver", 13): {"rush_att": 0, "receptions": 4, "targets": 5, "team": "TEN"}},
        "QB": {("Cam Ward", 13): {"rush_att": 3, "pass_att": 30, "team": "TEN"}},
    }
    totals = team_usage_totals(stat_lines_by_position)
    assert totals[("TEN", 13)] == {"targets": 7, "rush_att": 15, "receptions": 5, "pass_att": 30}


def test_team_usage_totals_skips_lines_with_no_team():
    stat_lines_by_position = {"RB": {("Nobody", 13): {"rush_att": 5, "team": ""}}}
    assert team_usage_totals(stat_lines_by_position) == {}


def test_team_usage_totals_keys_by_team_and_week_independently():
    stat_lines_by_position = {
        "RB": {
            ("Tony Pollard", 13): {"rush_att": 10, "receptions": 0, "targets": 0, "team": "TEN"},
            ("Tony Pollard", 14): {"rush_att": 20, "receptions": 0, "targets": 0, "team": "TEN"},
        }
    }
    totals = team_usage_totals(stat_lines_by_position)
    assert totals[("TEN", 13)]["rush_att"] == 10
    assert totals[("TEN", 14)]["rush_att"] == 20


# -- compute_touches -----------------------------------------------------------


def test_compute_touches_sums_rush_att_and_receptions():
    assert compute_touches({"rush_att": 12, "receptions": 3}) == 15


def test_compute_touches_none_when_rush_att_key_missing():
    assert compute_touches({}) is None


# -- compute_share_pcts --------------------------------------------------------
#
# TGTSHARE = player targets / team's combined pass attempts (the team's own
# QB(s) PASSING_ATT, not a sum of recorded targets).
# TOUCHSHARE = (player carries + player receptions) / (team carries + team
# receptions).
# OPPSHARE = (player carries + player targets) / (team carries + team
# targets).


def test_compute_share_pcts_divides_by_own_teams_total():
    team_totals = {("TEN", 13): {"targets": 7, "rush_att": 15, "receptions": 5, "pass_att": 30}}
    stat_line = {"targets": 2, "rush_att": 12, "receptions": 1, "team": "TEN"}
    target_pct, touch_pct, opp_pct = compute_share_pcts(stat_line, team_totals=team_totals, team="TEN", week=13)
    assert target_pct == round(2 / 30 * 100, 1)
    assert touch_pct == round((12 + 1) / (15 + 5) * 100, 1)
    assert opp_pct == round((12 + 2) / (15 + 7) * 100, 1)


def test_compute_share_pcts_none_when_team_total_missing():
    stat_line = {"targets": 2, "rush_att": 12, "receptions": 1, "team": "TEN"}
    target_pct, touch_pct, opp_pct = compute_share_pcts(stat_line, team_totals={}, team="TEN", week=13)
    assert target_pct is None
    assert touch_pct is None
    assert opp_pct is None


def test_compute_share_pcts_target_none_when_no_targets_key_but_touch_and_opp_still_compute():
    # QB's own stat line has no "targets" key at all -- target_share_pct
    # stays None (no FantasyData file ever carries a QB's own targets),
    # but touch_share_pct/opp_share_pct still compute as carries-only
    # shares, same "missing category treated as 0" precedent compute_touches
    # already uses for a QB's missing receptions.
    team_totals = {("TEN", 13): {"targets": 7, "rush_att": 15, "receptions": 5, "pass_att": 30}}
    stat_line = {"rush_att": 3, "team": "TEN"}
    target_pct, touch_pct, opp_pct = compute_share_pcts(stat_line, team_totals=team_totals, team="TEN", week=13)
    assert target_pct is None
    assert touch_pct == round(3 / 20 * 100, 1)
    assert opp_pct == round(3 / 22 * 100, 1)


def test_compute_share_pcts_none_when_denominator_is_zero():
    # A team total exists but a specific metric's own denominator is 0
    # (e.g. no QB stat line at all that week, so pass_att is 0) -- that
    # one metric goes None rather than dividing by zero, independent of
    # the other two.
    team_totals = {("TEN", 13): {"targets": 7, "rush_att": 15, "receptions": 5, "pass_att": 0}}
    stat_line = {"targets": 2, "rush_att": 12, "receptions": 1, "team": "TEN"}
    target_pct, touch_pct, opp_pct = compute_share_pcts(stat_line, team_totals=team_totals, team="TEN", week=13)
    assert target_pct is None
    assert touch_pct == round(13 / 20 * 100, 1)
    assert opp_pct == round(14 / 22 * 100, 1)


# -- compute_usage_share_updates -----------------------------------------------


def test_compute_usage_share_updates_aggregates_whole_team_not_just_one_position():
    # Only RB and QB stat lines are "requested," but the WR's own line
    # must still count toward the team total -- shares are meaningless
    # without seeing the whole team's offense for that week.
    stat_lines_by_position = {
        "RB": {
            ("Tony Pollard", 13): {
                "rush_att": 12,
                "receptions": 1,
                "targets": 2,
                "team": "TEN",
            }
        },
        "WR": {
            ("Wide Receiver", 13): {
                "rush_att": 0,
                "receptions": 4,
                "targets": 5,
                "team": "TEN",
            }
        },
        "QB": {("Cam Ward", 13): {"rush_att": 3, "pass_att": 30, "team": "TEN"}},
    }
    updates = compute_usage_share_updates(stat_lines_by_position, week=13)

    pollard_target, pollard_touch, pollard_opp = updates["RB"]["Tony Pollard"]
    assert pollard_target == round(2 / 30 * 100, 1)
    assert pollard_touch == round(13 / 20 * 100, 1)
    assert pollard_opp == round(14 / 22 * 100, 1)

    cam_target, cam_touch, cam_opp = updates["QB"]["Cam Ward"]
    assert cam_target is None  # QB has no targets key at all
    assert cam_touch == round(3 / 20 * 100, 1)
    assert cam_opp == round(3 / 22 * 100, 1)


def test_compute_usage_share_updates_only_includes_requested_week():
    stat_lines_by_position = {
        "RB": {
            ("Tony Pollard", 13): {"rush_att": 10, "receptions": 0, "targets": 0, "team": "TEN"},
            ("Tony Pollard", 14): {"rush_att": 20, "receptions": 0, "targets": 0, "team": "TEN"},
        }
    }
    updates = compute_usage_share_updates(stat_lines_by_position, week=13)
    assert list(updates["RB"].keys()) == ["Tony Pollard"]


def test_compute_usage_share_updates_omits_position_with_no_rows_for_week():
    stat_lines_by_position = {"RB": {("Tony Pollard", 14): {"rush_att": 10, "team": "TEN"}}}
    updates = compute_usage_share_updates(stat_lines_by_position, week=13)
    assert updates == {}
