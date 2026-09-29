from backend.schemas.ownership.ownership import GameBlock, OwnershipPlayer
from backend.services.ownership.game_blocks import (
    GAME_BLOCK_POSITIONS,
    GAME_BLOCK_QB_POSITION,
    MAX_GAME_BLOCKS_SAFETY_CAP,
    compute_game_blocks,
    filter_by_bringback_size,
    filter_game_blocks_by_max_salary,
    filter_game_blocks_by_salary_buckets,
)


def make_player(player, position, team, opponent, salary, expected_fpts=None):
    return OwnershipPlayer(
        player=player,
        position=position,
        team=team,
        opponent=opponent,
        is_home=True,
        salary=salary,
        ownership_pct=10.0,
        expected_fpts=expected_fpts,
    )


def test_game_block_positions_are_rb_wr_te_only():
    assert GAME_BLOCK_POSITIONS == {"RB", "WR", "TE"}


def test_compute_game_blocks_excludes_qb_and_dst():
    players = [
        make_player("QB1", "QB", "HOU", "ARI", 8000),
        make_player("DST1", "DST", "HOU", "ARI", 3000),
        make_player("RB1", "RB", "HOU", "ARI", 5000),
        make_player("RB2", "RB", "ARI", "HOU", 4000),
    ]
    blocks, skipped = compute_game_blocks(players)
    assert skipped == []
    for block in blocks:
        for p in block.players:
            assert p.position in {"RB", "WR", "TE"}


def test_compute_game_blocks_requires_both_teams():
    # All 3 players on the same team -- no combination of 2 or 3 can ever
    # include both teams, so no blocks should be produced at all.
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "WR", "HOU", "ARI", 4000),
        make_player("C", "TE", "HOU", "ARI", 3000),
    ]
    blocks, skipped = compute_game_blocks(players)
    assert blocks == []
    # Not a "skipped" game -- it just can't ever qualify at any size, a
    # different reason than the safety cap (see that test below).
    assert skipped == []


def test_compute_game_blocks_generates_every_both_teams_combo():
    # 2 players per team -- every size-2 combo that isn't both-same-team
    # should appear (2x2 = 4 cross-team pairs; same-team pairs excluded).
    players = [
        make_player("A1", "RB", "HOU", "ARI", 5000),
        make_player("A2", "WR", "HOU", "ARI", 4000),
        make_player("B1", "RB", "ARI", "HOU", 3000),
        make_player("B2", "WR", "ARI", "HOU", 2000),
    ]
    blocks, _skipped = compute_game_blocks(players, min_size=2, max_size=2)
    pairs = {frozenset(p.player for p in b.players) for b in blocks}
    assert pairs == {
        frozenset({"A1", "B1"}),
        frozenset({"A1", "B2"}),
        frozenset({"A2", "B1"}),
        frozenset({"A2", "B2"}),
    }


def test_compute_game_blocks_never_mixes_games():
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "ARI", "HOU", 4000),
        make_player("C", "RB", "SF", "LAR", 3000),
        make_player("D", "RB", "LAR", "SF", 2000),
    ]
    blocks, _skipped = compute_game_blocks(players, min_size=2, max_size=2)
    for block in blocks:
        teams = {p.team for p in block.players}
        opponents = {p.opponent for p in block.players}
        assert teams | opponents in ({"HOU", "ARI"}, {"SF", "LAR"})


def test_compute_game_blocks_labels_larger_side_as_primary():
    players = [
        make_player("A1", "RB", "HOU", "ARI", 5000),
        make_player("A2", "WR", "HOU", "ARI", 4000),
        make_player("A3", "TE", "HOU", "ARI", 3000),
        make_player("B1", "RB", "ARI", "HOU", 2000),
    ]
    blocks, _skipped = compute_game_blocks(players, min_size=4, max_size=4)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.primary_team == "HOU"
    assert block.primary_count == 3
    assert block.bringback_team == "ARI"
    assert block.bringback_count == 1


def test_compute_game_blocks_even_split_breaks_alphabetically():
    players = [
        make_player("A1", "RB", "LAR", "ARI", 5000),
        make_player("A2", "WR", "LAR", "ARI", 4000),
        make_player("B1", "RB", "ARI", "LAR", 3000),
        make_player("B2", "WR", "ARI", "LAR", 2000),
    ]
    blocks, _skipped = compute_game_blocks(players, min_size=4, max_size=4)
    assert len(blocks) == 1
    # 2-2 split -- alphabetically first team (ARI) is "primary".
    assert blocks[0].primary_team == "ARI"
    assert blocks[0].bringback_team == "LAR"


def test_compute_game_blocks_sorted_by_total_salary_descending():
    players = [
        make_player("A1", "RB", "HOU", "ARI", 5000),
        make_player("A2", "WR", "HOU", "ARI", 4000),
        make_player("B1", "RB", "ARI", "HOU", 3000),
        make_player("B2", "WR", "ARI", "HOU", 1000),
    ]
    blocks, _skipped = compute_game_blocks(players, min_size=2, max_size=2)
    totals = [b.total_salary for b in blocks]
    assert totals == sorted(totals, reverse=True)


def test_compute_game_blocks_sums_expected_fpts():
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000, expected_fpts=20.0),
        make_player("B", "WR", "ARI", "HOU", 4000, expected_fpts=15.0),
    ]
    blocks, _skipped = compute_game_blocks(players, min_size=2, max_size=2)
    assert blocks[0].total_expected_fpts == 35.0


def test_compute_game_blocks_skips_games_past_safety_cap_without_failing():
    # 20 RB/WR/TE players per team (40 total, one game) blows well past
    # the safety cap across sizes 2-5 -- that game should be skipped
    # (reported in `skipped`), not raise and block everything.
    players = [make_player(f"A{i}", "WR", "HOU", "ARI", 5000) for i in range(20)]
    players += [make_player(f"B{i}", "WR", "ARI", "HOU", 5000) for i in range(20)]
    blocks, skipped = compute_game_blocks(players)
    assert blocks == []
    assert skipped == [frozenset({"HOU", "ARI"})]


def test_compute_game_blocks_skipping_one_game_does_not_affect_others():
    oversized = [make_player(f"A{i}", "WR", "HOU", "ARI", 5000) for i in range(20)]
    oversized += [make_player(f"B{i}", "WR", "ARI", "HOU", 5000) for i in range(20)]
    small_game = [
        make_player("C1", "RB", "SF", "LAR", 5000),
        make_player("C2", "RB", "LAR", "SF", 4000),
    ]
    blocks, skipped = compute_game_blocks(oversized + small_game)
    assert skipped == [frozenset({"HOU", "ARI"})]
    assert {p.player for b in blocks for p in b.players} == {"C1", "C2"}


def test_compute_game_blocks_default_excludes_qb_even_when_present():
    # include_qb defaults to False -- a QB in the pool shouldn't sneak into
    # blocks or change anything about existing behavior.
    players = [
        make_player("QB1", "QB", "HOU", "ARI", 8000),
        make_player("RB1", "RB", "HOU", "ARI", 5000),
        make_player("RB2", "RB", "ARI", "HOU", 4000),
    ]
    blocks, skipped = compute_game_blocks(players, min_size=2, max_size=2)
    assert skipped == []
    assert len(blocks) == 1
    assert {p.player for p in blocks[0].players} == {"RB1", "RB2"}


def test_compute_game_blocks_include_qb_adds_qb_as_extra_slot():
    # QB doesn't count toward min_size/max_size -- a size-2 RB/WR combo
    # plus the QB should end up as a 3-player block.
    players = [
        make_player("QB1", "QB", "HOU", "ARI", 8000),
        make_player("RB1", "RB", "HOU", "ARI", 5000),
        make_player("RB2", "RB", "ARI", "HOU", 4000),
    ]
    blocks, skipped = compute_game_blocks(players, min_size=2, max_size=2, include_qb=True)
    assert skipped == []
    assert len(blocks) == 1
    block = blocks[0]
    assert len(block.players) == 3
    assert {p.player for p in block.players} == {"QB1", "RB1", "RB2"}
    assert block.total_salary == 8000 + 5000 + 4000


def test_compute_game_blocks_include_qb_generates_one_block_per_qb_candidate():
    # Both teams have an eligible QB -- every RB/WR/TE combo should appear
    # once per QB, not just once total.
    players = [
        make_player("QB1", "QB", "HOU", "ARI", 8000),
        make_player("QB2", "QB", "ARI", "HOU", 7000),
        make_player("RB1", "RB", "HOU", "ARI", 5000),
        make_player("RB2", "RB", "ARI", "HOU", 4000),
    ]
    blocks, skipped = compute_game_blocks(players, min_size=2, max_size=2, include_qb=True)
    assert skipped == []
    assert len(blocks) == 2
    qb_names_used = {qb.player for b in blocks for qb in b.players if qb.position == "QB"}
    assert qb_names_used == {"QB1", "QB2"}


def test_compute_game_blocks_include_qb_skips_games_with_no_eligible_qb():
    # No QB at all in the pool for this game -- with include_qb on, this
    # game can't produce any block (every block now requires one), but
    # that's not a "skipped" (safety-cap) game -- same class as the
    # <2-teams case.
    players = [
        make_player("RB1", "RB", "HOU", "ARI", 5000),
        make_player("RB2", "RB", "ARI", "HOU", 4000),
    ]
    blocks, skipped = compute_game_blocks(players, min_size=2, max_size=2, include_qb=True)
    assert blocks == []
    assert skipped == []


def test_compute_game_blocks_include_qb_only_uses_qbs_from_the_same_game():
    # A QB from an unrelated game shouldn't leak into this game's blocks.
    players = [
        make_player("QB1", "QB", "HOU", "ARI", 8000),
        make_player("RB1", "RB", "HOU", "ARI", 5000),
        make_player("RB2", "RB", "ARI", "HOU", 4000),
        make_player("QB_other", "QB", "SF", "LAR", 7500),
    ]
    blocks, _skipped = compute_game_blocks(players, min_size=2, max_size=2, include_qb=True)
    assert len(blocks) == 1
    assert {p.player for p in blocks[0].players} == {"QB1", "RB1", "RB2"}


def test_compute_game_blocks_include_qb_lists_qb_first_regardless_of_salary():
    # QB1's salary (8000) is already the highest here, so also cover the
    # case where a QB is cheaper than the RB/WR/TE players -- it should
    # still be listed first.
    players = [
        make_player("QB1", "QB", "HOU", "ARI", 3000),
        make_player("RB1", "RB", "HOU", "ARI", 5000),
        make_player("RB2", "RB", "ARI", "HOU", 4000),
    ]
    blocks, _skipped = compute_game_blocks(players, min_size=2, max_size=2, include_qb=True)
    assert len(blocks) == 1
    assert blocks[0].players[0].player == "QB1"


def test_game_block_qb_position_constant():
    assert GAME_BLOCK_QB_POSITION == "QB"


def test_max_game_blocks_safety_cap_is_higher_than_position_blocks_cap():
    # This module's pool mixes 2-3 positions across both teams, so a
    # legitimately-filtered request routinely produces far more
    # combinations than position_blocks.py's single-position cap allows --
    # see this module's own docstring for why that cap wouldn't fit here.
    from backend.services.ownership.position_blocks import MAX_BLOCKS_SAFETY_CAP

    assert MAX_GAME_BLOCKS_SAFETY_CAP > MAX_BLOCKS_SAFETY_CAP


def _block(total_salary: int, bringback_count: int = 1) -> GameBlock:
    return GameBlock(
        players=[],
        total_salary=total_salary,
        primary_team="HOU",
        primary_count=3,
        bringback_team="ARI",
        bringback_count=bringback_count,
    )


def test_filter_by_bringback_size_no_sizes_returns_all():
    blocks = [_block(1000, 1), _block(2000, 2)]
    assert filter_by_bringback_size(blocks, []) == blocks


def test_filter_by_bringback_size_keeps_only_matching_sizes():
    blocks = [_block(1000, 1), _block(2000, 2), _block(3000, 3)]
    filtered = filter_by_bringback_size(blocks, [1, 3])
    assert [b.total_salary for b in filtered] == [1000, 3000]


def test_filter_game_blocks_by_max_salary_keeps_at_or_under():
    blocks = [_block(46000), _block(48000), _block(48001)]
    filtered = filter_game_blocks_by_max_salary(blocks, 48000)
    assert [b.total_salary for b in filtered] == [46000, 48000]


def test_filter_game_blocks_by_max_salary_empty_when_none_qualify():
    blocks = [_block(49000), _block(50000)]
    assert filter_game_blocks_by_max_salary(blocks, 48000) == []


def test_filter_game_blocks_by_salary_buckets_no_buckets_returns_all():
    blocks = [_block(1000), _block(50000)]
    assert filter_game_blocks_by_salary_buckets(blocks, [], cap=50000) == blocks


def test_filter_game_blocks_by_salary_buckets_keeps_only_matching_range():
    blocks = [_block(9999), _block(10000), _block(14999), _block(15000)]
    filtered = filter_game_blocks_by_salary_buckets(blocks, ["20_30"], cap=50000)
    assert [b.total_salary for b in filtered] == [10000, 14999]
