import pytest

from backend.schemas.ownership.ownership import OwnershipPlayer, PositionBlock
from backend.services.ownership.position_blocks import (
    ALLOWED_BLOCK_SIZES,
    SALARY_CAPS,
    compute_position_blocks,
    filter_blocks_by_salary_buckets,
    filter_blocks_by_same_team_size,
    game_key,
    game_label,
    salary_bucket_range,
    validate_block_size,
)


def make_player(player, position, team, opponent, salary, expected_fpts=None, is_home=True):
    return OwnershipPlayer(
        player=player,
        position=position,
        team=team,
        opponent=opponent,
        is_home=is_home,
        salary=salary,
        ownership_pct=10.0,
        expected_fpts=expected_fpts,
    )


def test_validate_block_size_rejects_unsupported_position():
    with pytest.raises(ValueError, match="RB, WR, or TE"):
        validate_block_size("QB", 2)


def test_validate_block_size_rejects_size_not_allowed_for_position():
    with pytest.raises(ValueError, match="TE"):
        validate_block_size("TE", 3)


def test_validate_block_size_accepts_every_allowed_combo():
    for position, sizes in ALLOWED_BLOCK_SIZES.items():
        for size in sizes:
            validate_block_size(position, size)  # no raise


def test_game_key_is_order_independent():
    a = make_player("A", "RB", "HOU", "ARI", 5000)
    b = make_player("B", "RB", "ARI", "HOU", 5000)
    assert game_key(a) == game_key(b)


def test_game_label_puts_away_team_first():
    # team="LAR" is_home=True -> LAR is the home team, ARI is away.
    player = make_player("A", "RB", "LAR", "ARI", 5000, is_home=True)
    assert game_label(player) == "ARI @ LAR"


def test_game_label_reflects_away_team_perspective_too():
    # Same real matchup, but from the away team's own player row --
    # team="ARI" is_home=False -> still "ARI @ LAR".
    player = make_player("B", "RB", "ARI", "LAR", 5000, is_home=False)
    assert game_label(player) == "ARI @ LAR"


def test_game_label_falls_back_to_alphabetical_vs_when_is_home_unknown():
    player = make_player("A", "RB", "LAR", "ARI", 5000, is_home=None)
    assert game_label(player) == "ARI vs LAR"


def test_compute_position_blocks_generates_every_combination_with_total_salary():
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "ARI", "HOU", 4000),
        make_player("C", "RB", "SF", "LAR", 3000),
    ]
    blocks = compute_position_blocks(players, block_size=2, same_game_only=False)

    assert len(blocks) == 3  # 3 choose 2
    totals = sorted(b.total_salary for b in blocks)
    assert totals == [7000, 8000, 9000]


def test_compute_position_blocks_sorted_by_total_salary_descending():
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "ARI", "HOU", 4000),
        make_player("C", "RB", "SF", "LAR", 3000),
    ]
    blocks = compute_position_blocks(players, block_size=2, same_game_only=False)
    totals = [b.total_salary for b in blocks]
    assert totals == sorted(totals, reverse=True)


def test_compute_position_blocks_players_within_block_sorted_by_salary_descending():
    players = [
        make_player("Cheap", "RB", "HOU", "ARI", 4000),
        make_player("Expensive", "RB", "ARI", "HOU", 6000),
    ]
    blocks = compute_position_blocks(players, block_size=2, same_game_only=False)
    assert [p.player for p in blocks[0].players] == ["Expensive", "Cheap"]


def test_compute_position_blocks_same_game_only_never_mixes_games():
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "ARI", "HOU", 4000),
        make_player("C", "RB", "SF", "LAR", 3000),
        make_player("D", "RB", "LAR", "SF", 2000),
    ]
    blocks = compute_position_blocks(players, block_size=2, same_game_only=True)

    # Only the 2 in-game pairs qualify -- A+B and C+D, not the 4
    # cross-game pairs that "any game" would also include.
    assert len(blocks) == 2
    for block in blocks:
        names = {p.player for p in block.players}
        assert names in ({"A", "B"}, {"C", "D"})


def test_compute_position_blocks_same_game_only_drops_lone_players():
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "ARI", "HOU", 4000),
        make_player("Lonely", "RB", "SF", "LAR", 3000),
    ]
    blocks = compute_position_blocks(players, block_size=2, same_game_only=True)
    assert len(blocks) == 1
    assert {p.player for p in blocks[0].players} == {"A", "B"}


def test_compute_position_blocks_raises_past_safety_cap():
    # 100 choose 3 is far past the safety cap.
    players = [make_player(f"P{i}", "RB", "HOU", "ARI", 5000) for i in range(100)]
    with pytest.raises(ValueError, match="narrow the team/position/game filters"):
        compute_position_blocks(players, block_size=3, same_game_only=False)


def test_compute_position_blocks_sums_expected_fpts_when_present():
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000, expected_fpts=20.0),
        make_player("B", "RB", "ARI", "HOU", 4000, expected_fpts=16.0),
    ]
    blocks = compute_position_blocks(players, block_size=2, same_game_only=False)
    assert blocks[0].total_expected_fpts == 36.0


def test_compute_position_blocks_expected_fpts_defaults_to_zero_when_absent():
    # Players with no expected_fpts set (the common case for every caller
    # except Salary Blocks' own endpoint) shouldn't blow up -- they just
    # contribute 0.0 to the block's total.
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "ARI", "HOU", 4000),
    ]
    blocks = compute_position_blocks(players, block_size=2, same_game_only=False)
    assert blocks[0].total_expected_fpts == 0.0


def test_salary_caps_has_draftkings_and_fanduel():
    assert SALARY_CAPS["DraftKings"] == 50000
    assert SALARY_CAPS["FanDuel"] == 60000


def test_salary_bucket_range_resolves_against_cap():
    # DK cap ($50,000): 20-30% is $10,000-$15,000.
    assert salary_bucket_range("20_30", cap=50000) == (10000.0, 15000.0)


def test_salary_bucket_range_top_bucket_is_open_ended():
    min_dollar, max_dollar = salary_bucket_range("60_plus", cap=50000)
    assert min_dollar == 30000.0
    assert max_dollar is None


def test_salary_bucket_range_scales_with_platform_cap():
    # Same bucket, FanDuel's $60,000 cap: 20-30% is $12,000-$18,000.
    assert salary_bucket_range("20_30", cap=60000) == (12000.0, 18000.0)


def test_salary_bucket_range_unknown_bucket_raises():
    with pytest.raises(ValueError, match="Unknown salary bucket"):
        salary_bucket_range("not_a_bucket", cap=50000)


def _block(total_salary: int) -> PositionBlock:
    return PositionBlock(players=[], total_salary=total_salary)


def test_filter_blocks_by_salary_buckets_no_buckets_returns_all():
    blocks = [_block(1000), _block(50000)]
    assert filter_blocks_by_salary_buckets(blocks, [], cap=50000) == blocks


def test_filter_blocks_by_salary_buckets_keeps_only_matching_range():
    blocks = [_block(9999), _block(10000), _block(14999), _block(15000)]
    # 20-30% of $50,000 is [10000, 15000).
    filtered = filter_blocks_by_salary_buckets(blocks, ["20_30"], cap=50000)
    assert [b.total_salary for b in filtered] == [10000, 14999]


def test_filter_blocks_by_salary_buckets_top_bucket_is_inclusive_of_boundary_and_up():
    blocks = [_block(29999), _block(30000), _block(100000)]
    filtered = filter_blocks_by_salary_buckets(blocks, ["60_plus"], cap=50000)
    assert [b.total_salary for b in filtered] == [30000, 100000]


def test_filter_blocks_by_salary_buckets_multiple_buckets_are_unioned():
    blocks = [_block(5000), _block(11000), _block(21000), _block(40000)]
    filtered = filter_blocks_by_salary_buckets(blocks, ["under_20", "40_50"], cap=50000)
    # under_20 = [0, 10000) matches 5000; 40_50 = [20000, 25000) matches
    # 21000. 11000 falls in 20_30 (not selected) and 40000 falls in 60_plus
    # (not selected), so both are excluded.
    assert [b.total_salary for b in filtered] == [5000, 21000]


def _team_block(*teams: str) -> PositionBlock:
    players = [make_player(f"P{i}", "RB", team, "OPP", 5000) for i, team in enumerate(teams)]
    return PositionBlock(players=players, total_salary=sum(p.salary for p in players))


def test_filter_blocks_by_same_team_size_no_sizes_returns_all():
    blocks = [_team_block("KC", "BUF"), _team_block("KC", "KC")]
    assert filter_blocks_by_same_team_size(blocks, []) == blocks


def test_filter_blocks_by_same_team_size_all_different_teams_is_one():
    blocks = [_team_block("KC", "BUF", "SF")]
    assert filter_blocks_by_same_team_size(blocks, [1]) == blocks
    assert filter_blocks_by_same_team_size(blocks, [2]) == []


def test_filter_blocks_by_same_team_size_keeps_only_matching_group_size():
    two_same = _team_block("KC", "KC", "BUF")
    all_different = _team_block("KC", "BUF", "SF")
    all_same = _team_block("KC", "KC", "KC")
    blocks = [two_same, all_different, all_same]

    assert filter_blocks_by_same_team_size(blocks, [2]) == [two_same]
    assert filter_blocks_by_same_team_size(blocks, [1]) == [all_different]
    assert filter_blocks_by_same_team_size(blocks, [3]) == [all_same]
    assert filter_blocks_by_same_team_size(blocks, [1, 2]) == [two_same, all_different]
