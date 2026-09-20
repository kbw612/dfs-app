from backend.schemas.dk_players.dk_players import DkPlayerRow, DkPlayersWeekStatus
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.contest_results.contest_standings_parser import ContestReferenceRow
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv, serialize_dk_players_csv
from backend.services.dk_players.dk_players_engine import (
    add_week_players_rows,
    apply_name_alias,
    calculate_week_points,
    derive_roster_position,
    name_lookup_candidates,
    suggest_stat_file_match,
    week_status,
)
from backend.services.dk_players.weekly_stats_loader import load_weekly_stat_lines, merge_td_points, parse_weekly_stats_csv


def make_salary_player(player, position, salary, team="TM"):
    return OwnershipPlayer(
        player=player, position=position, team=team, opponent="OPP", is_home=True, salary=salary, ownership_pct=None
    )


def make_row(name, week, salary=5000, pct_drafted=0.0, fpts=0.0, non_td_fpts=0.0, td_fpts=0.0, position="RB"):
    return DkPlayerRow(
        name=name,
        position=position,
        roster_position=derive_roster_position(position),
        team="TM",
        week=week,
        salary=salary,
        pct_drafted=pct_drafted,
        fpts=fpts,
        non_td_fpts=non_td_fpts,
        td_fpts=td_fpts,
    )


# -- derive_roster_position / apply_name_alias ----------------------------


def test_derive_roster_position_adds_flex_for_flex_eligible_positions():
    assert derive_roster_position("RB") == "RB/FLEX"
    assert derive_roster_position("WR") == "WR/FLEX"
    assert derive_roster_position("TE") == "TE/FLEX"


def test_derive_roster_position_leaves_qb_and_dst_unchanged():
    assert derive_roster_position("QB") == "QB"
    assert derive_roster_position("DST") == "DST"


def test_apply_name_alias_maps_known_alias_and_passes_through_unknown():
    aliases = {"James Cook III": "James Cook"}
    assert apply_name_alias("James Cook III", aliases) == "James Cook"
    assert apply_name_alias("Josh Allen", aliases) == "Josh Allen"


# -- name_lookup_candidates ---------------------------------------------------


def test_name_lookup_candidates_raw_name_first():
    aliases = {"James Cook III": "James Cook"}
    assert name_lookup_candidates("James Cook III", aliases) == ["James Cook III", "James Cook"]


def test_name_lookup_candidates_reverse_when_name_is_the_canonical():
    # Same alias entry, but this time the row itself is already spelled the
    # *canonical* way -- the reverse mapping should surface the alias
    # spelling as a fallback candidate.
    aliases = {"James Cook III": "James Cook"}
    assert name_lookup_candidates("James Cook", aliases) == ["James Cook", "James Cook III"]


def test_name_lookup_candidates_no_alias_at_all():
    assert name_lookup_candidates("Josh Allen", {}) == ["Josh Allen"]


# -- suggest_stat_file_match --------------------------------------------------


def test_suggest_stat_file_match_finds_shared_last_name_ignoring_suffix():
    assert suggest_stat_file_match("James Cook III", ["James Cook", "Josh Allen"]) == "James Cook"


def test_suggest_stat_file_match_finds_close_typo_without_shared_last_name():
    assert suggest_stat_file_match("Unknown Runner", ["Unknown Runnar"]) == "Unknown Runnar"


def test_suggest_stat_file_match_returns_none_when_nothing_close():
    assert suggest_stat_file_match("Drake London", ["Josh Allen", "Bijan Robinson"]) is None


def test_suggest_stat_file_match_returns_none_for_empty_candidates():
    assert suggest_stat_file_match("Drake London", []) is None


def test_suggest_stat_file_match_picks_closest_among_shared_surname_collision():
    # Two "Higgins"es -- should pick whichever shares a first name with
    # the target rather than an arbitrary one.
    candidates = ["Tee Higgins", "Jayden Higgins"]
    assert suggest_stat_file_match("Tee Higgins Jr.", candidates) == "Tee Higgins"


def test_suggest_stat_file_match_rejects_shared_surname_with_unrelated_first_name():
    # Real false positive seen on production data: two entirely different
    # players ("Tyreek Hill", "Taysom Hill") sharing a common surname is
    # not evidence of a typo -- a shared last name alone must not be
    # enough to suggest a match.
    assert suggest_stat_file_match("Tyreek Hill", ["Taysom Hill"]) is None


def test_suggest_stat_file_match_rejects_close_but_different_full_name():
    # Real false positive seen on production data: "Marvin Harrison Jr."
    # and "Marvin Mims Jr." share a first name and suffix (textually
    # similar overall) but are different players with different
    # surnames -- must not be suggested as a match.
    assert suggest_stat_file_match("Marvin Harrison Jr.", ["Marvin Mims Jr."]) is None


# -- CSV round trip ---------------------------------------------------------


def test_dk_players_csv_round_trip():
    rows = [make_row("Josh Allen", week=1, salary=7200, position="QB"), make_row("Bijan Robinson", week=1, salary=8000)]
    csv_text = serialize_dk_players_csv(rows)
    parsed = parse_dk_players_csv(csv_text)
    assert parsed == rows


def test_parse_dk_players_csv_empty_string_returns_empty_list():
    assert parse_dk_players_csv("") == []
    assert parse_dk_players_csv("   ") == []


def test_parse_dk_players_csv_accepts_percent_suffixed_pct_drafted():
    # A legacy/hand-copied DK-Players.csv (e.g. a prior season's export)
    # commonly writes %Drafted as "24.21%" rather than this app's own
    # bare-number storage format -- see _parse_pct_drafted's own
    # docstring. This used to raise ValueError and surface as an
    # unhandled 500 on every endpoint reading the tracker.
    csv_text = (
        "Name,Position,Roster Position,TeamAbbrev,Week,Salary,%Drafted,FPTS,Non_TD_FPTS,TD_FPTS\n"
        "Josh Allen,QB,QB,BUF,1,7200,24.21%,30.5,18.5,12.0\n"
        "Bijan Robinson,RB,RB/FLEX,ATL,1,8000,0%,0.0,0.0,0.0\n"
    )
    rows = parse_dk_players_csv(csv_text)
    assert rows[0].pct_drafted == 24.21
    assert rows[1].pct_drafted == 0.0


# -- week_status -------------------------------------------------------------


def test_week_status_reports_not_exists_for_unseen_week():
    status = week_status([], week=1)
    assert status == DkPlayersWeekStatus(week=1, exists=False, player_count=0, has_calculated_points=False)


def test_week_status_reports_calculated_points():
    rows = [make_row("Josh Allen", week=1, fpts=20.0)]
    status = week_status(rows, week=1)
    assert status.exists is True
    assert status.player_count == 1
    assert status.has_calculated_points is True


def test_week_status_not_calculated_when_still_zeroed():
    rows = [make_row("Josh Allen", week=1)]
    status = week_status(rows, week=1)
    assert status.has_calculated_points is False


# -- add_week_players_rows ---------------------------------------------------


def test_add_week_players_rows_fresh_week():
    salary_players = [make_salary_player("Josh Allen", "QB", 7200), make_salary_player("Bijan Robinson", "RB", 8000)]
    new_rows, result = add_week_players_rows([], salary_players, week=1)
    assert result.week == 1
    assert result.added_count == 2
    assert result.replaced is False
    assert {r.name for r in new_rows} == {"Josh Allen", "Bijan Robinson"}
    assert all(r.pct_drafted == 0.0 and r.fpts == 0.0 and r.td_fpts == 0.0 for r in new_rows)
    qb_row = next(r for r in new_rows if r.name == "Josh Allen")
    assert qb_row.roster_position == "QB"
    rb_row = next(r for r in new_rows if r.name == "Bijan Robinson")
    assert rb_row.roster_position == "RB/FLEX"


def test_add_week_players_rows_replaces_existing_week_and_keeps_other_weeks():
    existing = [make_row("Old Guy", week=1, fpts=15.0), make_row("Keep Me", week=2)]
    salary_players = [make_salary_player("New Guy", "WR", 6000)]
    new_rows, result = add_week_players_rows(existing, salary_players, week=1)
    assert result.replaced is True
    assert result.added_count == 1
    names_by_week = {(r.name, r.week) for r in new_rows}
    assert ("Keep Me", 2) in names_by_week
    assert ("New Guy", 1) in names_by_week
    assert ("Old Guy", 1) not in names_by_week


# -- weekly_stats_loader ------------------------------------------------------

QB_HEADER = "RK,NAME,TEAM,POS,WK,OPP,PASSING_CMP,PASSING_ATT,PASSING_CMP%,PASSING_YDS,PASSING_AVG,PASSING_TD,INT,LONG,SCK,RATING,RUSHING_ATT,RUSHING_YDS,RUSHING_AVG,RUSHING_TD,FPTS"
RB_HEADER = "RK,NAME,TEAM,POS,WK,OPP,RUSHING_ATT,RUSHING_YDS,RUSHING_AVG,RUSHING_TD,RECEIVING_TGTS,RECEIVING_REC,RECEIVING_YDS,RECEIVING_TD,FUMBLES,FUMBLES_LOST,FPTS"


def test_parse_weekly_stats_csv_qb_computes_passing_and_rushing_td_points():
    csv_text = f"{QB_HEADER}\n1,Lamar Jackson,BAL,QB,1,BUF,14,19,73.7,209,11.0,2,0,39,2,144.4,6,70,11.7,1,29.4\n"
    result = parse_weekly_stats_csv(csv_text, week=1)
    # 2 passing TD * 4 + 1 rushing TD * 6 = 14
    assert result == {"Lamar Jackson": 14.0}


def test_parse_weekly_stats_csv_rb_computes_rushing_and_receiving_td_points():
    csv_text = f"{RB_HEADER}\n2,Bijan Robinson,ATL,RB,1,TB,12,24,2.0,0,7,6,100,1,0,0,24.4\n"
    result = parse_weekly_stats_csv(csv_text, week=1)
    # 0 rushing TD + 1 receiving TD * 6 = 6
    assert result == {"Bijan Robinson": 6.0}


def test_parse_weekly_stats_csv_filters_by_week():
    csv_text = f"{RB_HEADER}\n1,Someone,ATL,RB,2,TB,10,50,5.0,1,0,0,0,0,0,0,10.0\n"
    assert parse_weekly_stats_csv(csv_text, week=1) == {}


def test_parse_weekly_stats_csv_blank_cells_parse_as_zero():
    # RUSHING_AVG blank when RUSHING_ATT is 0 -- shouldn't affect TD parsing.
    csv_text = f"{RB_HEADER}\n1,Someone,ATL,RB,1,TB,0,0,,0,5,4,40,0,0,0,8.0\n"
    assert parse_weekly_stats_csv(csv_text, week=1) == {"Someone": 0.0}


def test_merge_td_points_combines_all_position_files():
    qb_csv = f"{QB_HEADER}\n1,Lamar Jackson,BAL,QB,1,BUF,14,19,73.7,209,11.0,2,0,39,2,144.4,6,70,11.7,1,29.4\n"
    rb_csv = f"{RB_HEADER}\n2,Bijan Robinson,ATL,RB,1,TB,12,24,2.0,0,7,6,100,1,0,0,24.4\n"
    merged = merge_td_points({"QB": qb_csv, "RB": rb_csv}, week=1)
    assert merged == {"Lamar Jackson": 14.0, "Bijan Robinson": 6.0}


def test_load_weekly_stat_lines_reads_every_week_at_once():
    csv_text = (
        f"{RB_HEADER}\n"
        "1,Tony Pollard,TEN,RB,13,CLE,12,60,5.0,0,2,1,3,0,0,0,6.3\n"
        "1,Tony Pollard,TEN,RB,14,SF,18,101,5.6,1,2,2,15,0,0,0,21.6\n"
    )
    lines = load_weekly_stat_lines(csv_text)
    assert lines[("Tony Pollard", 13)] == {
        "rush_att": 12,
        "rush_yards": 60,
        "targets": 2,
        "receptions": 1,
        "receiving_yards": 3,
        "team": "TEN",
    }
    assert lines[("Tony Pollard", 14)]["rush_att"] == 18


def test_load_weekly_stat_lines_qb_file_has_no_receiving_keys():
    csv_text = f"{QB_HEADER}\n1,Lamar Jackson,BAL,QB,1,BUF,14,19,73.7,209,11.0,2,0,39,2,144.4,6,70,11.7,1,29.4\n"
    lines = load_weekly_stat_lines(csv_text)
    stat_line = lines[("Lamar Jackson", 1)]
    assert stat_line["rush_att"] == 6
    assert stat_line["rush_yards"] == 70
    assert stat_line["team"] == "BAL"
    assert "targets" not in stat_line
    assert "receptions" not in stat_line
    assert "receiving_yards" not in stat_line


def test_load_weekly_stat_lines_qb_file_includes_passing_line():
    csv_text = f"{QB_HEADER}\n1,Lamar Jackson,BAL,QB,1,BUF,14,19,73.7,209,11.0,2,0,39,2,144.4,6,70,11.7,1,29.4\n"
    lines = load_weekly_stat_lines(csv_text)
    stat_line = lines[("Lamar Jackson", 1)]
    assert stat_line["pass_cmp"] == 14
    assert stat_line["pass_att"] == 19
    assert stat_line["pass_cmp_pct"] == 73.7
    assert stat_line["pass_yds"] == 209
    assert stat_line["pass_avg"] == 11.0
    assert stat_line["pass_td"] == 2
    assert stat_line["pass_int"] == 0
    assert stat_line["pass_sck"] == 2
    assert stat_line["pass_rtg"] == 144.4


def test_load_weekly_stat_lines_non_qb_file_has_no_passing_keys():
    # RB's file has no PASSING_*/INT/SCK/RATING columns at all -- same
    # "missing column -> key simply omitted" convention as the receiving
    # columns being absent from the QB file.
    csv_text = f"{RB_HEADER}\n2,Bijan Robinson,ATL,RB,1,TB,12,24,2.0,0,7,6,100,1,0,0,24.4\n"
    lines = load_weekly_stat_lines(csv_text)
    stat_line = lines[("Bijan Robinson", 1)]
    for key in ("pass_cmp", "pass_att", "pass_cmp_pct", "pass_yds", "pass_avg", "pass_td", "pass_int", "pass_sck", "pass_rtg"):
        assert key not in stat_line


def test_load_weekly_stat_lines_blank_cells_parse_as_zero():
    csv_text = f"{RB_HEADER}\n1,Someone,ATL,RB,1,TB,0,0,,0,5,4,40,0,0,0,8.0\n"
    lines = load_weekly_stat_lines(csv_text)
    assert lines[("Someone", 1)]["rush_att"] == 0


def test_load_weekly_stat_lines_reads_precomputed_share_columns():
    # TGT_SHARE/TOUCH_SHARE/OPP_SHARE are three extra trailing columns "Calc Week Points &
    # Fantasy Data" writes (see usage_shares.compute_usage_share_updates +
    # weekly_stats_repo.write_usage_share_columns) -- once present, a real
    # value parses as a float.
    csv_text = (
        f"{RB_HEADER},TGT_SHARE,TOUCH_SHARE,OPP_SHARE\n2,Bijan Robinson,ATL,RB,1,TB,12,24,2.0,0,7,6,100,1,0,0,24.4,28.6,65.0,50.0\n"
    )
    lines = load_weekly_stat_lines(csv_text)
    stat_line = lines[("Bijan Robinson", 1)]
    assert stat_line["target_share_pct"] == 28.6
    assert stat_line["touch_share_pct"] == 65.0
    assert stat_line["opp_share_pct"] == 50.0


def test_load_weekly_stat_lines_blank_share_cells_parse_as_none_not_zero():
    # A blank TGT_SHARE/TOUCH_SHARE/OPP_SHARE cell means "not yet calculated" (or, for
    # TGT_SHARE, "not applicable" for a QB row) -- unlike every other numeric
    # column in this file, this must NOT default to 0.
    csv_text = f"{RB_HEADER},TGT_SHARE,TOUCH_SHARE,OPP_SHARE\n2,Bijan Robinson,ATL,RB,1,TB,12,24,2.0,0,7,6,100,1,0,0,24.4,,,\n"
    lines = load_weekly_stat_lines(csv_text)
    stat_line = lines[("Bijan Robinson", 1)]
    assert stat_line["target_share_pct"] is None
    assert stat_line["touch_share_pct"] is None
    assert stat_line["opp_share_pct"] is None


def test_load_weekly_stat_lines_omits_share_keys_when_columns_missing():
    # An older file, or a week "Calc Week Points" hasn't run for yet --
    # no TGT_SHARE/TOUCH_SHARE/OPP_SHARE header at all, so the keys are simply absent
    # (not None) from the stat line, same "not applicable yet" convention
    # as every other optional column in this file.
    csv_text = f"{RB_HEADER}\n2,Bijan Robinson,ATL,RB,1,TB,12,24,2.0,0,7,6,100,1,0,0,24.4\n"
    lines = load_weekly_stat_lines(csv_text)
    stat_line = lines[("Bijan Robinson", 1)]
    assert "target_share_pct" not in stat_line
    assert "touch_share_pct" not in stat_line
    assert "opp_share_pct" not in stat_line


# -- calculate_week_points ----------------------------------------------------


def test_calculate_week_points_uses_contest_fpts_and_subtracts_td_points():
    existing = [make_row("Lamar Jackson", week=1, position="QB")]
    contest_rows = [ContestReferenceRow(player="Lamar Jackson", roster_position="QB", pct_drafted=4.89, fpts=29.36)]
    td_points = {"Lamar Jackson": 14.0}

    updated_rows, result = calculate_week_points(existing, week=1, td_points_by_player=td_points, contest_rows=contest_rows, name_aliases={})

    assert result.updated_count == 1
    assert result.possible_stat_name_mismatches == []
    assert result.no_stats_recorded == []
    assert result.unmatched_contest_players == []
    row = updated_rows[0]
    assert row.pct_drafted == 4.89
    assert row.fpts == 29.36
    assert row.td_fpts == 14.0
    assert row.non_td_fpts == 15.36  # 29.36 - 14.0


def test_calculate_week_points_only_touches_requested_week():
    existing = [make_row("Lamar Jackson", week=1, position="QB"), make_row("Other Guy", week=2)]
    contest_rows = [ContestReferenceRow(player="Lamar Jackson", roster_position="QB", pct_drafted=4.89, fpts=29.36)]
    updated_rows, result = calculate_week_points(existing, week=1, td_points_by_player={"Lamar Jackson": 14.0}, contest_rows=contest_rows, name_aliases={})
    week2_row = next(r for r in updated_rows if r.name == "Other Guy")
    assert week2_row.fpts == 0.0  # untouched


def test_calculate_week_points_reports_no_stats_recorded_when_stat_file_empty():
    # No stat data at all for this position/week -- nothing to suggest a
    # close match from, so this lands in no_stats_recorded, not
    # possible_stat_name_mismatches (see suggest_stat_file_match).
    existing = [make_row("Mystery Guy", week=1)]
    contest_rows = [ContestReferenceRow(player="Mystery Guy", roster_position="RB", pct_drafted=2.0, fpts=10.0)]
    updated_rows, result = calculate_week_points(existing, week=1, td_points_by_player={}, contest_rows=contest_rows, name_aliases={})
    assert result.no_stats_recorded == ["Mystery Guy"]
    assert result.possible_stat_name_mismatches == []
    assert result.unmatched_contest_players == []
    row = updated_rows[0]
    assert row.fpts == 10.0
    assert row.td_fpts == 0.0  # fell back to existing (zeroed) value
    assert row.non_td_fpts == 10.0


def test_calculate_week_points_reports_unmatched_contest_player():
    existing = [make_row("Mystery Guy", week=1)]
    updated_rows, result = calculate_week_points(existing, week=1, td_points_by_player={"Mystery Guy": 6.0}, contest_rows=[], name_aliases={})
    assert result.unmatched_contest_players == ["Mystery Guy"]
    assert result.possible_stat_name_mismatches == []
    assert result.no_stats_recorded == []
    row = updated_rows[0]
    assert row.fpts == 0.0  # fell back to existing (zeroed) value
    assert row.td_fpts == 6.0
    assert row.non_td_fpts == -6.0  # 0 - 6, arithmetically honest about a partial match


def test_calculate_week_points_leaves_fully_unmatched_row_untouched():
    existing = [make_row("Nobody Knows", week=1, salary=4000)]
    updated_rows, result = calculate_week_points(existing, week=1, td_points_by_player={}, contest_rows=[], name_aliases={})
    assert result.updated_count == 0
    assert updated_rows[0] == existing[0]


def test_calculate_week_points_applies_name_alias_to_match_stat_and_contest_names():
    # Tracker (from the Salary File) has "James Cook III" -- FantasyData
    # and Contest Standings both spell it "James Cook".
    existing = [make_row("James Cook III", week=1)]
    contest_rows = [ContestReferenceRow(player="James Cook", roster_position="RB", pct_drafted=10.0, fpts=18.0)]
    td_points = {"James Cook": 6.0}
    aliases = {"James Cook III": "James Cook"}

    updated_rows, result = calculate_week_points(existing, week=1, td_points_by_player=td_points, contest_rows=contest_rows, name_aliases=aliases)

    assert result.updated_count == 1
    row = updated_rows[0]
    assert row.name == "James Cook III"  # the tracker's own row identity is untouched
    assert row.fpts == 18.0
    assert row.td_fpts == 6.0


def test_calculate_week_points_contest_matches_raw_name_when_stat_file_needs_the_alias():
    # Real-world case that motivated name_lookup_candidates: Contest
    # Standings actually agrees with the tracker's own "James Cook III"
    # spelling (no translation needed there), while only the stat file
    # drops the suffix to "James Cook". A single alias translation applied
    # to both sources used to break the contest lookup that would have
    # matched natively -- this confirms each source is tried on its own.
    existing = [make_row("James Cook III", week=1)]
    contest_rows = [ContestReferenceRow(player="James Cook III", roster_position="RB", pct_drafted=2.98, fpts=34.1)]
    td_points = {"James Cook": 18.0}
    aliases = {"James Cook III": "James Cook"}

    updated_rows, result = calculate_week_points(
        existing, week=1, td_points_by_player=td_points, contest_rows=contest_rows, name_aliases=aliases
    )

    assert result.possible_stat_name_mismatches == []
    assert result.no_stats_recorded == []
    assert result.unmatched_contest_players == []
    row = updated_rows[0]
    assert row.pct_drafted == 2.98
    assert row.fpts == 34.1
    assert row.td_fpts == 18.0
    assert row.non_td_fpts == 16.1  # 34.1 - 18.0


def test_calculate_week_points_falls_back_to_reverse_alias_mapping():
    # Opposite direction from the above -- the tracker row is already
    # spelled the *canonical* way, but a source is keyed by the alias's
    # own spelling instead. The reverse candidate should still find it.
    existing = [make_row("James Cook", week=1)]
    contest_rows = [ContestReferenceRow(player="James Cook III", roster_position="RB", pct_drafted=2.98, fpts=34.1)]
    td_points = {"James Cook": 18.0}
    aliases = {"James Cook III": "James Cook"}

    updated_rows, result = calculate_week_points(
        existing, week=1, td_points_by_player=td_points, contest_rows=contest_rows, name_aliases=aliases
    )

    assert result.possible_stat_name_mismatches == []
    assert result.no_stats_recorded == []
    assert result.unmatched_contest_players == []
    row = updated_rows[0]
    assert row.pct_drafted == 2.98
    assert row.fpts == 34.1
    assert row.td_fpts == 18.0


def test_calculate_week_points_missing_stat_file_reported_once_not_per_player():
    # Two RB players, no RB stat file uploaded at all -- both should be
    # excluded from unmatched_stat_players (that's not a name-mismatch
    # problem) and "RB" should show up once in missing_stat_files instead.
    existing = [make_row("Player A", week=1), make_row("Player B", week=1)]
    contest_rows = [
        ContestReferenceRow(player="Player A", roster_position="RB", pct_drafted=5.0, fpts=10.0),
        ContestReferenceRow(player="Player B", roster_position="RB", pct_drafted=3.0, fpts=8.0),
    ]
    updated_rows, result = calculate_week_points(
        existing, week=1, td_points_by_player={}, contest_rows=contest_rows, name_aliases={}, missing_stat_positions=["RB"]
    )
    assert result.missing_stat_files == ["RB"]
    assert result.possible_stat_name_mismatches == []
    assert result.no_stats_recorded == []
    # FPTS/%Drafted still update from the contest data even though TD
    # data is unavailable -- TD_FPTS just stays at its prior (zeroed) value.
    assert updated_rows[0].fpts == 10.0
    assert updated_rows[0].td_fpts == 0.0
    assert updated_rows[0].non_td_fpts == 10.0


def test_calculate_week_points_reports_no_stats_recorded_when_file_present_but_nothing_close():
    # RB file WAS uploaded, but nothing in it is even close to this
    # player's name -- a genuine "didn't play" case, not a spelling
    # problem, so this lands in no_stats_recorded.
    existing = [make_row("Unknown Runner", week=1)]
    contest_rows = [ContestReferenceRow(player="Unknown Runner", roster_position="RB", pct_drafted=5.0, fpts=10.0)]
    _updated_rows, result = calculate_week_points(
        existing, week=1, td_points_by_player={"Someone Else": 6.0}, contest_rows=contest_rows, name_aliases={}, missing_stat_positions=[]
    )
    assert result.missing_stat_files == []
    assert result.no_stats_recorded == ["Unknown Runner"]
    assert result.possible_stat_name_mismatches == []


def test_calculate_week_points_reports_possible_stat_name_mismatch_for_a_close_typo():
    # RB file has this exact player under a slightly different spelling --
    # no name alias configured for it, but the fuzzy check should still
    # surface it as a suggested match worth aliasing, not silently lump it
    # in with genuine non-matches.
    existing = [make_row("Unknown Runner", week=1)]
    contest_rows = [ContestReferenceRow(player="Unknown Runner", roster_position="RB", pct_drafted=5.0, fpts=10.0)]
    _updated_rows, result = calculate_week_points(
        existing, week=1, td_points_by_player={"Unknown Runnar": 6.0}, contest_rows=contest_rows, name_aliases={}
    )
    assert result.no_stats_recorded == []
    assert len(result.possible_stat_name_mismatches) == 1
    mismatch = result.possible_stat_name_mismatches[0]
    assert mismatch.tracker_name == "Unknown Runner"
    assert mismatch.suggested_match == "Unknown Runnar"


def test_calculate_week_points_never_flags_dst_in_either_stat_list():
    existing = [make_row("Packers", week=1, position="DST")]
    contest_rows = [ContestReferenceRow(player="Packers", roster_position="DST", pct_drafted=10.0, fpts=7.0)]
    updated_rows, result = calculate_week_points(
        existing, week=1, td_points_by_player={}, contest_rows=contest_rows, name_aliases={}, missing_stat_positions=["QB", "RB", "WR", "TE"]
    )
    assert result.possible_stat_name_mismatches == []
    assert result.no_stats_recorded == []
    assert updated_rows[0].fpts == 7.0
    assert updated_rows[0].td_fpts == 0.0
    assert updated_rows[0].non_td_fpts == 7.0


def test_calculate_week_points_aggregates_pct_drafted_across_roster_slots():
    # Same real-world quirk as Contest Results' ownership rank -- a player
    # used at both RB and FLEX across different entries has two partial
    # reference rows; their true ownership is the sum.
    existing = [make_row("Bijan Robinson", week=1)]
    contest_rows = [
        ContestReferenceRow(player="Bijan Robinson", roster_position="RB", pct_drafted=5.0, fpts=27.4),
        ContestReferenceRow(player="Bijan Robinson", roster_position="FLEX", pct_drafted=3.0, fpts=27.4),
    ]
    updated_rows, _result = calculate_week_points(existing, week=1, td_points_by_player={}, contest_rows=contest_rows, name_aliases={})
    assert updated_rows[0].pct_drafted == 8.0
