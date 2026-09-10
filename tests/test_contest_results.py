from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.contest_results.contest_results_engine import build_contest_result_rows, build_top_lineups
from backend.services.contest_results.contest_standings_parser import (
    ContestReferenceRow,
    ContestStandings,
    parse_contest_standings_csv,
    parse_lineup_text,
)

HEADER = "Rank,EntryId,EntryName,TimeRemaining,Points,Lineup,,Player,Roster Position,%Drafted,FPTS"


def make_player(player, position, salary, team="TM", opponent="OPP"):
    return OwnershipPlayer(
        player=player, position=position, team=team, opponent=opponent, is_home=True, salary=salary, ownership_pct=None
    )


def test_parse_lineup_text_splits_on_fixed_slot_order():
    text = (
        "DST Packers  FLEX TreVeyon Henderson QB Trevor Lawrence RB D'Andre Swift "
        "RB Tyrone Tracy Jr. TE Dalton Schultz WR Puka Nacua WR Jameson Williams WR DJ Moore"
    )
    pairs = parse_lineup_text(text)
    assert pairs == [
        ("DST", "Packers"),
        ("FLEX", "TreVeyon Henderson"),
        ("QB", "Trevor Lawrence"),
        ("RB", "D'Andre Swift"),
        ("RB", "Tyrone Tracy Jr."),
        ("TE", "Dalton Schultz"),
        ("WR", "Puka Nacua"),
        ("WR", "Jameson Williams"),
        ("WR", "DJ Moore"),
    ]


def test_parse_lineup_text_tolerates_double_space_before_slot_token():
    # The real export's own Lineup field has a stray double space between
    # a DST's team name and the next slot token -- shouldn't leak into
    # the DST's own name or break the next pair.
    pairs = parse_lineup_text("DST Packers  FLEX Bijan Robinson")
    assert pairs == [("DST", "Packers"), ("FLEX", "Bijan Robinson")]


def test_parse_lineup_text_empty_string_returns_empty_list():
    assert parse_lineup_text("") == []


def test_parse_contest_standings_csv_parses_entries_and_reference_rows():
    csv_text = (
        f"{HEADER}\n"
        "1,111,alice,0,50.0,DST Packers FLEX Bijan Robinson,,Bijan Robinson,FLEX,49.69%,7.30\n"
        "2,222,bob,0,45.0,DST Bears FLEX Puka Nacua,,Puka Nacua,WR,36.46%,30.90\n"
    )
    standings = parse_contest_standings_csv(csv_text)

    assert [e.rank for e in standings.entries] == [1, 2]
    assert standings.entries[0].entry_name == "alice"
    assert standings.entries[0].points == 50.0
    assert standings.entries[0].lineup_text == "DST Packers FLEX Bijan Robinson"

    assert standings.reference_rows == [
        ContestReferenceRow(player="Bijan Robinson", roster_position="FLEX", pct_drafted=49.69, fpts=7.30),
        ContestReferenceRow(player="Puka Nacua", roster_position="WR", pct_drafted=36.46, fpts=30.90),
    ]


def test_parse_contest_standings_csv_handles_ragged_rows_where_one_side_runs_out():
    # Entries table longer than the reference table -- later rows have
    # nothing in the Player/Roster Position/%Drafted/FPTS columns at all.
    csv_text = (
        f"{HEADER}\n"
        "1,111,alice,0,50.0,DST Packers,,Bijan Robinson,FLEX,49.69%,7.30\n"
        "2,222,bob,0,45.0,DST Bears,,,,,\n"
    )
    standings = parse_contest_standings_csv(csv_text)
    assert len(standings.entries) == 2
    assert len(standings.reference_rows) == 1


def test_parse_contest_standings_csv_handles_short_rows_missing_trailing_columns():
    # A row with fewer than 11 columns at all (e.g. a trailing blank line
    # that still has *some* commas) shouldn't raise an IndexError.
    csv_text = f"{HEADER}\n1,111,alice,0,50.0,DST Packers\n"
    standings = parse_contest_standings_csv(csv_text)
    assert len(standings.entries) == 1
    assert standings.entries[0].lineup_text == "DST Packers"
    assert standings.reference_rows == []


def _standings_for_one_lineup(lineup_text: str, points: float, reference_rows: list[ContestReferenceRow]) -> ContestStandings:
    from backend.services.contest_results.contest_standings_parser import ContestEntry

    return ContestStandings(
        entries=[ContestEntry(rank=1, entry_id="1", entry_name="alice", points=points, lineup_text=lineup_text)],
        reference_rows=reference_rows,
    )


def test_build_top_lineups_joins_salary_and_reference_data():
    standings = _standings_for_one_lineup(
        "DST Packers FLEX Bijan Robinson",
        points=38.30,
        reference_rows=[
            ContestReferenceRow(player="Packers", roster_position="DST", pct_drafted=10.0, fpts=7.0),
            ContestReferenceRow(player="Bijan Robinson", roster_position="FLEX", pct_drafted=49.69, fpts=7.30),
        ],
    )
    salary_players = [make_player("Packers", "DST", 3800), make_player("Bijan Robinson", "RB", 7700)]

    lineups = build_top_lineups(standings, salary_players, top_n=10)
    assert len(lineups) == 1
    lu = lineups[0]
    assert lu.rank == 1
    assert lu.points == 38.30

    dst, flex = lu.players
    assert dst.roster_position == "DST"
    assert dst.player == "Packers"
    assert dst.salary == 3800
    assert dst.position == "DST"
    assert dst.pct_drafted == 10.0
    assert dst.exp_pts == 15.2  # 3800 / 1000 * 4.0
    assert dst.act_pts == 7.0
    assert dst.diff == 7.0 - 15.2

    assert flex.salary == 7700
    assert flex.exp_pts == 30.8  # 7700 / 1000 * 4.0
    assert flex.act_pts == 7.30

    assert lu.total_salary == 3800 + 7700
    assert lu.total_pct_drafted == 10.0 + 49.69
    assert lu.total_exp_pts == 15.2 + 30.8
    assert lu.total_act_pts == 7.0 + 7.30
    assert lu.total_diff == lu.total_act_pts - lu.total_exp_pts


def test_build_top_lineups_unmatched_player_gets_none_fields_without_crashing():
    # "Mystery Player" isn't in the salary file OR the reference table --
    # every one of their fields comes back None, but the lineup still has
    # all 9 (well, 2 here) slots and the OTHER player's totals still sum.
    standings = _standings_for_one_lineup(
        "DST Packers FLEX Mystery Player",
        points=15.2,
        reference_rows=[ContestReferenceRow(player="Packers", roster_position="DST", pct_drafted=10.0, fpts=15.2)],
    )
    salary_players = [make_player("Packers", "DST", 3800)]

    lineups = build_top_lineups(standings, salary_players, top_n=10)
    lu = lineups[0]
    dst, flex = lu.players
    assert flex.player == "Mystery Player"
    assert flex.salary is None
    assert flex.position is None
    assert flex.pct_drafted is None
    assert flex.exp_pts is None
    assert flex.act_pts is None
    assert flex.diff is None

    # Totals only reflect the one player with real numbers.
    assert lu.total_salary == 3800
    assert lu.total_pct_drafted == 10.0
    assert lu.total_exp_pts == 15.2
    assert lu.total_act_pts == 15.2


def test_build_top_lineups_prefers_exact_slot_match_over_player_only_fallback():
    # Two reference rows for the same player at different slots (a real
    # scenario -- some entrants drafted them at RB, others as FLEX) --
    # the lineup used FLEX, so it should pick FLEX's own %Drafted, not
    # whichever row happens to come first.
    standings = _standings_for_one_lineup(
        "FLEX Bijan Robinson",
        points=7.30,
        reference_rows=[
            ContestReferenceRow(player="Bijan Robinson", roster_position="RB", pct_drafted=5.0, fpts=7.30),
            ContestReferenceRow(player="Bijan Robinson", roster_position="FLEX", pct_drafted=49.69, fpts=7.30),
        ],
    )
    salary_players = [make_player("Bijan Robinson", "RB", 7700)]

    lineups = build_top_lineups(standings, salary_players, top_n=10)
    assert lineups[0].players[0].pct_drafted == 49.69


def test_build_top_lineups_respects_top_n():
    from backend.services.contest_results.contest_standings_parser import ContestEntry

    standings = ContestStandings(
        entries=[
            ContestEntry(rank=i, entry_id=str(i), entry_name=f"e{i}", points=float(i), lineup_text="DST Packers")
            for i in range(1, 6)
        ],
        reference_rows=[],
    )
    lineups = build_top_lineups(standings, [], top_n=2)
    assert [lu.rank for lu in lineups] == [1, 2]


def test_build_contest_result_rows_joins_salary_and_attaches_week():
    standings = ContestStandings(
        entries=[],
        reference_rows=[
            ContestReferenceRow(player="Bijan Robinson", roster_position="FLEX", pct_drafted=49.69, fpts=7.30),
            ContestReferenceRow(player="Unmatched Guy", roster_position="WR", pct_drafted=1.0, fpts=0.0),
        ],
    )
    salary_players = [make_player("Bijan Robinson", "RB", 7700)]

    rows = build_contest_result_rows(standings, salary_players, week=15)
    assert rows[0].week == 15
    assert rows[0].player == "Bijan Robinson"
    assert rows[0].salary == 7700
    assert rows[0].roster_position == "FLEX"
    assert rows[0].pct_drafted == 49.69
    assert rows[0].fpts == 7.30

    assert rows[1].player == "Unmatched Guy"
    assert rows[1].salary is None


# -- LineupSummary --------------------------------------------------------


def test_lineup_summary_flex_position_reports_true_position():
    # FLEX's own true position (from the salary file) should surface even
    # though the roster slot itself is always just "FLEX".
    standings = _standings_for_one_lineup(
        "FLEX George Kittle",
        points=10.0,
        reference_rows=[ContestReferenceRow(player="George Kittle", roster_position="FLEX", pct_drafted=5.0, fpts=10.0)],
    )
    salary_players = [make_player("George Kittle", "TE", 6000)]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.flex_position == "TE"


def test_lineup_summary_overstack_same_team_no_bringback():
    # Two lineup players from the same team, none from the opponent --
    # "overstack" (this app's own term for a one-sided game stack).
    standings = _standings_for_one_lineup(
        "QB Trevor Lawrence RB Travis Etienne",
        points=30.0,
        reference_rows=[
            ContestReferenceRow(player="Trevor Lawrence", roster_position="QB", pct_drafted=8.0, fpts=20.0),
            ContestReferenceRow(player="Travis Etienne", roster_position="RB", pct_drafted=15.0, fpts=18.0),
        ],
    )
    salary_players = [
        make_player("Trevor Lawrence", "QB", 6500, team="JAX", opponent="TEN"),
        make_player("Travis Etienne", "RB", 7000, team="JAX", opponent="TEN"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert len(lu.summary.game_stacks) == 1
    stack = lu.summary.game_stacks[0]
    assert stack.kind == "overstack"
    assert stack.primary_team == "JAX"
    assert sorted(stack.primary_positions) == ["QB", "RB"]
    assert stack.bringback_team is None
    assert stack.bringback_positions == []


def test_lineup_summary_onslaught_both_teams_bringback():
    # One player from each side of the same game -- "onslaught", same
    # primary/bring-back split Salary Blocks' own Onslaught feature uses.
    standings = _standings_for_one_lineup(
        "RB Josh Jacobs WR Christian Watson",
        points=30.0,
        reference_rows=[
            ContestReferenceRow(player="Josh Jacobs", roster_position="RB", pct_drafted=20.0, fpts=22.0),
            ContestReferenceRow(player="Christian Watson", roster_position="WR", pct_drafted=9.0, fpts=25.0),
        ],
    )
    salary_players = [
        make_player("Josh Jacobs", "RB", 6800, team="GB", opponent="DET"),
        make_player("Christian Watson", "WR", 5500, team="DET", opponent="GB"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert len(lu.summary.game_stacks) == 1
    stack = lu.summary.game_stacks[0]
    assert stack.kind == "onslaught"
    assert {stack.primary_team, stack.bringback_team} == {"GB", "DET"}
    assert stack.primary_positions + stack.bringback_positions != []
    # Even 1-1 split -- ties break alphabetically by team (DET < GB).
    assert stack.primary_team == "DET"
    assert stack.primary_positions == ["WR"]
    assert stack.bringback_team == "GB"
    assert stack.bringback_positions == ["RB"]


def test_lineup_summary_single_player_in_a_game_is_not_a_stack():
    standings = _standings_for_one_lineup(
        "QB Trevor Lawrence",
        points=20.0,
        reference_rows=[ContestReferenceRow(player="Trevor Lawrence", roster_position="QB", pct_drafted=8.0, fpts=20.0)],
    )
    salary_players = [make_player("Trevor Lawrence", "QB", 6500, team="JAX", opponent="TEN")]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.game_stacks == []


def test_lineup_summary_dst_teammate_correlation():
    standings = _standings_for_one_lineup(
        "DST Packers WR Christian Watson",
        points=20.0,
        reference_rows=[
            ContestReferenceRow(player="Packers", roster_position="DST", pct_drafted=10.0, fpts=7.0),
            ContestReferenceRow(player="Christian Watson", roster_position="WR", pct_drafted=9.0, fpts=25.0),
        ],
    )
    salary_players = [
        make_player("Packers", "DST", 3000, team="GB", opponent="DET"),
        make_player("Christian Watson", "WR", 5500, team="GB", opponent="DET"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.dst_team == "GB"
    assert lu.summary.dst_teammates == ["Christian Watson"]


def test_lineup_summary_dst_with_no_teammates_reports_empty_list():
    standings = _standings_for_one_lineup(
        "DST Packers WR Christian Watson",
        points=20.0,
        reference_rows=[
            ContestReferenceRow(player="Packers", roster_position="DST", pct_drafted=10.0, fpts=7.0),
            ContestReferenceRow(player="Christian Watson", roster_position="WR", pct_drafted=9.0, fpts=25.0),
        ],
    )
    salary_players = [
        make_player("Packers", "DST", 3000, team="GB", opponent="DET"),
        make_player("Christian Watson", "WR", 5500, team="MIN", opponent="CHI"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.dst_team == "GB"
    assert lu.summary.dst_teammates == []


def test_lineup_summary_dst_opponent_correlation():
    # Christian Watson plays for DET, which is Packers' (GB) opponent --
    # rostering him alongside your own GB DST is betting on the offense
    # your DST is trying to shut down.
    standings = _standings_for_one_lineup(
        "DST Packers WR Christian Watson TE Sam LaPorta",
        points=20.0,
        reference_rows=[
            ContestReferenceRow(player="Packers", roster_position="DST", pct_drafted=10.0, fpts=7.0),
            ContestReferenceRow(player="Christian Watson", roster_position="WR", pct_drafted=9.0, fpts=25.0),
            ContestReferenceRow(player="Sam LaPorta", roster_position="TE", pct_drafted=6.0, fpts=12.0),
        ],
    )
    salary_players = [
        make_player("Packers", "DST", 3000, team="GB", opponent="DET"),
        make_player("Christian Watson", "WR", 5500, team="DET", opponent="GB"),
        make_player("Sam LaPorta", "TE", 5000, team="DET", opponent="GB"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.dst_opponent_team == "DET"
    assert lu.summary.dst_opponent_positions == ["WR", "TE"]


def test_lineup_summary_dst_no_opponent_players_reports_empty_list():
    standings = _standings_for_one_lineup(
        "DST Packers WR Justin Jefferson",
        points=20.0,
        reference_rows=[
            ContestReferenceRow(player="Packers", roster_position="DST", pct_drafted=10.0, fpts=7.0),
            ContestReferenceRow(player="Justin Jefferson", roster_position="WR", pct_drafted=30.0, fpts=28.0),
        ],
    )
    salary_players = [
        make_player("Packers", "DST", 3000, team="GB", opponent="DET"),
        make_player("Justin Jefferson", "WR", 8500, team="MIN", opponent="CHI"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.dst_opponent_team == "DET"
    assert lu.summary.dst_opponent_positions == []


def test_lineup_summary_qb_stacked_true_when_same_team_pass_catcher_rostered():
    standings = _standings_for_one_lineup(
        "QB Trevor Lawrence RB Travis Etienne",
        points=30.0,
        reference_rows=[
            ContestReferenceRow(player="Trevor Lawrence", roster_position="QB", pct_drafted=8.0, fpts=20.0),
            ContestReferenceRow(player="Travis Etienne", roster_position="RB", pct_drafted=15.0, fpts=18.0),
        ],
    )
    salary_players = [
        make_player("Trevor Lawrence", "QB", 6500, team="JAX", opponent="TEN"),
        make_player("Travis Etienne", "RB", 7000, team="JAX", opponent="TEN"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.qb_player == "Trevor Lawrence"
    assert lu.summary.qb_stacked is True


def test_lineup_summary_qb_played_naked_when_no_teammate_rostered():
    standings = _standings_for_one_lineup(
        "QB Trevor Lawrence RB Josh Jacobs",
        points=30.0,
        reference_rows=[
            ContestReferenceRow(player="Trevor Lawrence", roster_position="QB", pct_drafted=8.0, fpts=20.0),
            ContestReferenceRow(player="Josh Jacobs", roster_position="RB", pct_drafted=20.0, fpts=22.0),
        ],
    )
    salary_players = [
        make_player("Trevor Lawrence", "QB", 6500, team="JAX", opponent="TEN"),
        make_player("Josh Jacobs", "RB", 6800, team="GB", opponent="DET"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.qb_stacked is False


def test_lineup_summary_qb_stacked_none_when_qb_unmatched():
    standings = _standings_for_one_lineup(
        "QB Mystery Person",
        points=10.0,
        reference_rows=[],
    )
    lu = build_top_lineups(standings, [], top_n=1)[0]
    assert lu.summary.qb_player == "Mystery Person"
    assert lu.summary.qb_stacked is None


def test_lineup_summary_salary_leftover_vs_cap():
    standings = _standings_for_one_lineup(
        "QB Trevor Lawrence RB Josh Jacobs",
        points=30.0,
        reference_rows=[],
    )
    salary_players = [
        make_player("Trevor Lawrence", "QB", 20000, team="JAX", opponent="TEN"),
        make_player("Josh Jacobs", "RB", 25000, team="GB", opponent="DET"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.salary_leftover == 50000 - 45000


def test_lineup_summary_salary_leftover_none_when_a_player_salary_is_unknown():
    standings = _standings_for_one_lineup(
        "QB Trevor Lawrence RB Mystery Player",
        points=30.0,
        reference_rows=[],
    )
    salary_players = [make_player("Trevor Lawrence", "QB", 20000, team="JAX", opponent="TEN")]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.salary_leftover is None


def test_lineup_summary_distinct_games_and_teams():
    standings = _standings_for_one_lineup(
        "QB Trevor Lawrence RB Josh Jacobs WR Christian Watson",
        points=30.0,
        reference_rows=[],
    )
    salary_players = [
        make_player("Trevor Lawrence", "QB", 6500, team="JAX", opponent="TEN"),
        make_player("Josh Jacobs", "RB", 6800, team="GB", opponent="DET"),
        make_player("Christian Watson", "WR", 5500, team="DET", opponent="GB"),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.summary.distinct_teams == 3
    assert lu.summary.distinct_games == 2  # JAX@TEN, GB@DET (Watson shares Jacobs' game)


def test_player_rank_aggregates_pct_drafted_across_roster_slots():
    # Player A is drafted at both RB (10%) and FLEX (10%) across different
    # entries -- their TOTAL 20% usage should outrank Player B's single
    # 15% RB-only usage, even though neither of A's individual rows beats
    # B's on its own. Points work the other way (B scored more), showing
    # ownership_rank and points_rank are computed independently.
    standings = _standings_for_one_lineup(
        "RB Player B",
        points=10.0,
        reference_rows=[
            ContestReferenceRow(player="Player A", roster_position="RB", pct_drafted=10.0, fpts=5.0),
            ContestReferenceRow(player="Player A", roster_position="FLEX", pct_drafted=10.0, fpts=5.0),
            ContestReferenceRow(player="Player B", roster_position="RB", pct_drafted=15.0, fpts=9.0),
        ],
    )
    salary_players = [
        make_player("Player A", "RB", 7000),
        make_player("Player B", "RB", 6000),
    ]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    # Player B (in this lineup) should rank 2nd in ownership (20% > 15%)
    # despite Player A never appearing in this particular lineup.
    assert lu.players[0].ownership_rank == 2
    # But Player B's own actual FPTS (9.0) beats Player A's (5.0) --
    # points_rank is independent of ownership_rank.
    assert lu.players[0].points_rank == 1


def test_boom_bust_thresholds_on_diff():
    standings = _standings_for_one_lineup(
        "QB Boom Guy",
        points=10.0,
        reference_rows=[ContestReferenceRow(player="Boom Guy", roster_position="QB", pct_drafted=8.0, fpts=30.0)],
    )
    # 5000 salary -> Exp Pts = 20.0; Act Pts 30.0 -> Diff +10 -> boom.
    salary_players = [make_player("Boom Guy", "QB", 5000)]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.players[0].boom_bust == "boom"


def test_boom_bust_none_within_threshold():
    standings = _standings_for_one_lineup(
        "QB Steady Guy",
        points=10.0,
        reference_rows=[ContestReferenceRow(player="Steady Guy", roster_position="QB", pct_drafted=8.0, fpts=21.0)],
    )
    # 5000 salary -> Exp Pts = 20.0; Act Pts 21.0 -> Diff +1 -> neither.
    salary_players = [make_player("Steady Guy", "QB", 5000)]
    lu = build_top_lineups(standings, salary_players, top_n=1)[0]
    assert lu.players[0].boom_bust is None
