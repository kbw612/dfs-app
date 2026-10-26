import numpy as np
import pytest

from backend.services.lineup_analyzer.features import (
    FEATURE_NAMES,
    PoolArrays,
    feature_matrix,
    slot_ordered_names,
)
from backend.services.lineup_analyzer.weight_fit import WeekData, evaluate, fit_logistic, training_set


def _pool():
    """Pool indices: 0 QB(T0) 1 RB(T0) 2 RB(T1) 3-5 WR(T0,T1,T1) 6 TE(T2)
    7 WR(T3) 8 DST(T1). T0 plays T1 (game 0); T2 plays T3 (game 1)."""
    team = np.array([0, 0, 1, 0, 1, 1, 2, 3, 1], dtype=np.int32)
    opponent = np.array([1, 1, 0, 1, 0, 0, 3, 2, 0], dtype=np.int32)
    game = np.array([0, 0, 0, 0, 0, 0, 1, 1, 0], dtype=np.int32)
    return PoolArrays(
        names=[f"p{i}" for i in range(9)],
        ownership=np.array([10.0, 25.0, 2.0, 5.0, 30.0, 1.0, 12.0, 4.0, 8.0]),
        salary=np.array([6500, 7000, 4000, 6000, 8200, 3000, 4500, 5000, 2800]),
        team=team,
        opponent=opponent,
        game=game,
        is_skill=np.array([False, True, True, True, True, True, True, True, False]),
    )


def _features(lineup):
    row = feature_matrix(np.array([lineup], dtype=np.int32), _pool())[0]
    return dict(zip(FEATURE_NAMES, row))


def test_stack_bringback_and_game_stack():
    # slots: QB RB RB WR WR WR TE FLEX DST -> QB0, RB1, RB2, WR3, WR4, WR5, TE6, FLEX7, DST8
    f = _features([0, 1, 2, 3, 4, 5, 6, 7, 8])
    assert f["qb_mates"] == 2  # RB1 and WR3 share the QB's team
    assert f["bringback"] == 1  # RB2/WR4/WR5 are on the opposing team
    assert f["game_stack"] == 6  # QB0, 1, 2, 3, 4, 5 are all in game 0
    # DST8 is team 1; skill players facing team 1 are the team-0 ones (QB0, RB1, WR3).
    assert f["dst_conflict"] == 3


def test_ownership_and_salary_features():
    f = _features([0, 1, 2, 3, 4, 5, 6, 7, 8])
    assert f["own_sum"] == pytest.approx(97.0)
    assert f["max_own"] == 30.0 and f["qb_own"] == 10.0
    assert f["n_chalk"] == 2 and f["n_low"] == 2  # 25% and 30% / 2% and 1%
    assert f["unused_k"] == pytest.approx((50000 - 47000) / 1000)
    assert f["n_stars"] == 1 and f["n_punts"] == 3  # 8200 / 4000, 3000, 4500


def test_slot_ordered_names_follows_the_synthetic_slot_order():
    slots = [
        ("DST", "DST", "d"),
        ("FLEX", "WR", "f"),
        ("QB", "QB", "q"),
        ("RB", "RB", "r1"),
        ("RB", "RB", "r2"),
        ("TE", "TE", "t"),
        ("WR", "WR", "w1"),
        ("WR", "WR", "w2"),
        ("WR", "WR", "w3"),
    ]
    assert slot_ordered_names(slots) == ["q", "r1", "r2", "w1", "w2", "w3", "t", "f", "d"]


def test_logistic_fit_recovers_a_separating_direction():
    rng = np.random.default_rng(0)
    pos = rng.normal([1.0, 0.0], 1.0, size=(400, 2))
    neg = rng.normal([-1.0, 0.0], 1.0, size=(400, 2))
    x = np.vstack([pos, neg])
    y = np.concatenate([np.ones(400), np.zeros(400)])
    weights, _ = fit_logistic(x, y, l2=1.0)
    assert weights[0] > 1.0 and abs(weights[1]) < 0.4


def test_evaluate_ranks_real_lineups_against_the_weighted_field():
    rng = np.random.default_rng(1)
    field = rng.normal(0.0, 1.0, size=(2000, 1))
    real = rng.normal(2.0, 0.3, size=(200, 1))
    data = WeekData(1, real, field, np.full(2000, 1 / 2000))
    ev = evaluate(data, np.array([1.0]))
    assert ev.auc > 0.95 and ev.median_field_percentile > 95
    flipped = evaluate(data, np.array([-1.0]))
    assert flipped.auc < 0.05


def test_training_set_balances_real_and_field_rows():
    rng = np.random.default_rng(2)
    data = WeekData(1, rng.normal(size=(10, 3)), rng.normal(size=(500, 3)), np.full(500, 1 / 500))
    x, y = training_set([data], negatives_per_positive=3)
    assert x.shape == (40, 3) and int(y.sum()) == 10
