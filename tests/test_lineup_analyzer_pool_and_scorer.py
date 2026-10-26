import numpy as np

from backend.services.lineup_analyzer.pool_parser import lineup_key, parse_cell, parse_pool_csv
from backend.services.lineup_analyzer.scorer import build_portfolio, default_weights, tier
from backend.services.lineup_analyzer.features import FEATURE_NAMES


def test_parse_cell_with_and_without_id():
    assert parse_cell("Josh Allen (123)") == ("Josh Allen", "123")
    assert parse_cell("Raiders") == ("Raiders", "")


def test_parse_pool_reorders_to_canonical_slots_and_dedupes_by_player_set():
    header = "DST,QB,RB,RB,WR,WR,WR,TE,FLEX"
    row = "D (9),Q (1),R1 (2),R2 (3),W1 (4),W2 (5),W3 (6),T (7),F (8)"
    swapped = "D (9),Q (1),R2 (3),R1 (2),W1 (4),W2 (5),W3 (6),T (7),F (8)"
    bad = "D (9),Q (1)"
    lineups = parse_pool_csv("\n".join([header, row, swapped, bad]))
    assert len(lineups) == 2
    assert [n for n, _ in lineups[0]] == ["Q", "R1", "R2", "W1", "W2", "W3", "T", "F", "D"]
    assert lineup_key(lineups[0]) == lineup_key(lineups[1])


def test_parse_pool_rejects_wrong_header():
    try:
        parse_pool_csv("A,B\n1,2")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_default_weights_cover_all_features_and_prefer_spending_salary():
    w = default_weights()
    assert set(w) == set(FEATURE_NAMES) | {"proj_sum", "ceiling_sum", "qb_game_total", "avg_team_implied", "dst_opp_implied"}
    assert w["unused_k"] < 0


def test_tier_cutoffs():
    assert tier(99.95) == "Top 0.1% profile"
    assert tier(99.2) == "Top 1% profile"
    assert tier(10) == "Below"


def test_portfolio_respects_exposure_and_overlap():
    index = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8], [0, 1, 2, 3, 4, 5, 6, 7, 9], [0, 10, 11, 12, 13, 14, 15, 16, 17], [20, 21, 22, 23, 24, 25, 26, 27, 28]])
    order = np.arange(4)
    assert build_portfolio(index, order, 4, 100, 9) == [0, 1, 2, 3]
    assert build_portfolio(index, order, 4, 100, 7) == [0, 2, 3]  # lineup 1 shares 8
    assert build_portfolio(index, order, 4, 50, 9) == [0, 1, 3]  # cap 2 of 4: player 0 hits the cap after two lineups, so lineup 2 is blocked


def test_result_repo_roundtrip_and_delete(tmp_path):
    from backend.repositories.lineup_analyzer.pool_repo import delete_result, load_result, save_result

    assert load_result(tmp_path, 2026, 1, "DraftKings", "Classic Main") is None
    save_result(tmp_path, 2026, 1, "DraftKings", "Classic Main", {"a": 1})
    assert load_result(tmp_path, 2026, 1, "DraftKings", "Classic Main") == {"a": 1}
    assert load_result(tmp_path, 2026, 2, "DraftKings", "Classic Main") is None
    delete_result(tmp_path, 2026, 1, "DraftKings", "Classic Main")
    assert load_result(tmp_path, 2026, 1, "DraftKings", "Classic Main") is None
