import numpy as np
import pytest

from backend.services.lineup_analyzer.history_loader import HistoricalPlayer, HistoricalWeek
from backend.services.lineup_analyzer.synthetic_field import (
    SALARY_CAP,
    FieldParams,
    _flex_probabilities,
    exposure_error,
    generate_field,
)


def _player(name, pos, team, salary, pct, fpts):
    return HistoricalPlayer(name, pos, team, "", salary, None, pct, None, fpts)


def _week():
    """A small slate: 3 QB, 5 RB, 6 WR, 3 TE, 3 DST across 3 teams. Ownership
    sums to the real shape: QB/DST 100, RB 233, WR 330, TE 105 (so RB 33%,
    WR 30% and TE 5% of lineups have that FLEX)."""
    pool = {}
    for team, qb_pct in (("AAA", 50.0), ("BBB", 30.0), ("CCC", 20.0)):
        pool[f"QB {team}"] = _player(f"QB {team}", "QB", team, 6000, qb_pct, 18.0)
        pool[f"DST {team}"] = _player(f"DST {team}", "DST", team, 2800, 100 / 3, 7.0)
        pool[f"TE {team}"] = _player(f"TE {team}", "TE", team, 3800, 35.0, 8.0)
    for i, (team, pct) in enumerate((("AAA", 70.0), ("BBB", 60.0), ("CCC", 50.0), ("AAA", 33.0), ("BBB", 20.0))):
        pool[f"RB{i}"] = _player(f"RB{i}", "RB", team, 5000 + 200 * i, pct, 12.0 + i)
    for i, (team, pct) in enumerate((("AAA", 80.0), ("BBB", 70.0), ("CCC", 60.0), ("AAA", 50.0), ("BBB", 40.0), ("CCC", 30.0))):
        pool[f"WR{i}"] = _player(f"WR{i}", "WR", team, 4800 + 300 * i, pct, 10.0 + i)
    return HistoricalWeek(5, {"AAA", "BBB", "CCC"}, pool, [], True)


def test_flex_probabilities_come_from_position_ownership_totals():
    probs = _flex_probabilities(_week())
    assert probs["RB"] == pytest.approx(33 / 68, abs=0.01)
    assert probs["WR"] == pytest.approx(30 / 68, abs=0.01)
    assert probs["TE"] == pytest.approx(5 / 68, abs=0.01)


def test_lineups_are_valid_classic_rosters_under_the_cap():
    week = _week()
    field = generate_field(week, FieldParams(1.0, 0.0), n_lineups=4000, seed=1, fit_sample=4000, fit_rounds=2)
    positions = {name: week.pool[name].position for name in field.players}
    live = field.weights > 0
    assert live.sum() > 100
    assert (field.salary[live] <= SALARY_CAP).all()
    for row in field.lineups[live][:300]:
        assert len(set(row)) == 9  # nobody twice
        counts = {}
        for idx in row:
            counts[positions[field.players[idx]]] = counts.get(positions[field.players[idx]], 0) + 1
        assert counts["QB"] == 1 and counts["DST"] == 1
        assert counts["RB"] >= 2 and counts["WR"] >= 3 and counts["TE"] >= 1
        assert counts["RB"] + counts["WR"] + counts["TE"] == 7


def test_weights_sum_to_one_and_points_are_sums_of_actual_fpts():
    week = _week()
    field = generate_field(week, n_lineups=3000, seed=2, fit_sample=3000, fit_rounds=2)
    assert field.weights.sum() == pytest.approx(1.0)
    row = field.lineups[0]
    assert field.points[0] == pytest.approx(sum(week.pool[field.players[i]].fpts for i in row))


def test_exposure_is_fit_to_actual_ownership():
    week = _week()
    field = generate_field(week, FieldParams(0.0, 0.0), n_lineups=30000, seed=3, fit_sample=20000, fit_rounds=6)
    assert exposure_error(field, week) < 4.0  # percentage points, tiny slate


def test_stack_boost_raises_qb_teammates():
    week = _week()
    low = generate_field(week, FieldParams(0.0, 0.0), n_lineups=8000, seed=4, fit_sample=4000, fit_rounds=1)
    high = generate_field(week, FieldParams(0.0, 1.5), n_lineups=8000, seed=4, fit_sample=4000, fit_rounds=1)
    assert (high.weights * high.qb_teammates).sum() > (low.weights * low.qb_teammates).sum()


def test_cutoff_points_is_monotonic_in_fraction():
    week = _week()
    field = generate_field(week, n_lineups=5000, seed=5, fit_sample=3000, fit_rounds=1)
    assert field.cutoff_points(0.001) >= field.cutoff_points(0.01) >= field.cutoff_points(0.5)


def test_raises_when_a_position_has_no_drafted_players():
    week = _week()
    for name in [n for n, p in week.pool.items() if p.position == "TE"]:
        week.pool[name].actual_pct = 0.0
    with pytest.raises(ValueError):
        generate_field(week, n_lineups=1000, fit_sample=1000, fit_rounds=1)


def test_seed_makes_the_field_reproducible():
    week = _week()
    a = generate_field(week, n_lineups=2000, seed=9, fit_sample=2000, fit_rounds=1)
    b = generate_field(week, n_lineups=2000, seed=9, fit_sample=2000, fit_rounds=1)
    assert np.array_equal(a.lineups, b.lineups)
