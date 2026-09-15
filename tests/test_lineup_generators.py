from itertools import combinations

from backend.schemas.contest_results.contest_results import ContestResultRow
from backend.services.contest_results.lineup_generators import build_top10_by_points
from backend.services.contest_results.optimal_lineup import solve_lineup


def make_row(player, position, salary, fpts, week=1):
    return ContestResultRow(week=week, player=player, salary=salary, position=position, pct_drafted=0.0, fpts=fpts)


def _small_pool():
    # Same pool as tests/test_optimal_lineup.py's -- small but with real
    # salary/value trade-offs at every position.
    return [
        make_row("QB A", "QB", 3000, 20.0),
        make_row("QB B", "QB", 2500, 15.0),
        make_row("RB 1", "RB", 3000, 10.0),
        make_row("RB 2", "RB", 2000, 8.0),
        make_row("RB 3", "RB", 2500, 9.0),
        make_row("RB 4", "RB", 1500, 5.0),
        make_row("WR 1", "WR", 3000, 12.0),
        make_row("WR 2", "WR", 2000, 9.0),
        make_row("WR 3", "WR", 2500, 10.0),
        make_row("WR 4", "WR", 1500, 6.0),
        make_row("TE 1", "TE", 2000, 7.0),
        make_row("TE 2", "TE", 1500, 4.0),
        make_row("DST 1", "DST", 2000, 5.0),
        make_row("DST 2", "DST", 1500, 3.0),
    ]


def _all_legal_lineup_values(rows: list[ContestResultRow], cap: int) -> list[float]:
    """Every legal DK Classic lineup's total FPTS (not just the best),
    via full brute-force enumeration -- ground truth for cross-checking
    build_top10_by_points, independent of its own DP implementation."""
    by_position: dict[str, list[ContestResultRow]] = {}
    for row in rows:
        by_position.setdefault(row.position, []).append(row)

    values: list[float] = []
    for qb in combinations(by_position.get("QB", []), 1):
        for rb_count in (2, 3):
            for wr_count in (3, 4):
                for te_count in (1, 2):
                    extras = (rb_count - 2) + (wr_count - 3) + (te_count - 1)
                    if extras != 1:
                        continue
                    for rb in combinations(by_position.get("RB", []), rb_count):
                        for wr in combinations(by_position.get("WR", []), wr_count):
                            for te in combinations(by_position.get("TE", []), te_count):
                                for dst in combinations(by_position.get("DST", []), 1):
                                    group = qb + rb + wr + te + dst
                                    salary = sum(r.salary for r in group)
                                    if salary > cap:
                                        continue
                                    values.append(sum(r.fpts for r in group))
    return values


def test_build_top10_by_points_matches_brute_force_ranking():
    rows = _small_pool()
    cap = 20000
    top10 = build_top10_by_points(rows, salary_cap=cap, k=10)
    all_values = sorted(_all_legal_lineup_values(rows, cap), reverse=True)

    got_values = [round(lu.total_fpts, 6) for lu in top10]
    expected_values = [round(v, 6) for v in all_values[:10]]
    assert got_values == expected_values


def test_build_top10_by_points_returns_distinct_lineups():
    rows = _small_pool()
    top10 = build_top10_by_points(rows, salary_cap=20000, k=10)
    keys = [frozenset(p.player for p in lu.players) for lu in top10]
    assert len(keys) == len(set(keys))


def test_build_top10_by_points_values_monotonically_decreasing():
    rows = _small_pool()
    top10 = build_top10_by_points(rows, salary_cap=20000, k=10)
    values = [lu.total_fpts for lu in top10]
    assert values == sorted(values, reverse=True)


def test_build_top10_by_points_first_lineup_matches_single_best_solve():
    rows = _small_pool()
    top10 = build_top10_by_points(rows, salary_cap=20000, k=10)
    single_best = solve_lineup(rows, salary_cap=20000)
    assert single_best is not None
    assert top10[0].total_fpts == single_best.total_fpts


def test_build_top10_by_points_returns_fewer_than_k_when_pool_is_thin():
    # Bare-minimum legal pool -- exactly enough players to build ONE
    # lineup (2 RB, 3 WR, 1 TE with no spares for FLEX variety, 1 QB, 1
    # DST) plus one extra RB just barely big enough for a single FLEX
    # swap -- only a handful of distinct legal lineups exist here, nowhere
    # near 10.
    rows = [
        make_row("QB A", "QB", 5000, 20.0),
        make_row("RB 1", "RB", 5000, 10.0),
        make_row("RB 2", "RB", 4000, 8.0),
        make_row("RB 3", "RB", 3000, 6.0),
        make_row("WR 1", "WR", 5000, 12.0),
        make_row("WR 2", "WR", 4000, 9.0),
        make_row("WR 3", "WR", 3000, 7.0),
        make_row("TE 1", "TE", 3000, 8.0),
        make_row("DST 1", "DST", 2000, 5.0),
    ]
    top10 = build_top10_by_points(rows, salary_cap=50000, k=10)
    assert 0 < len(top10) < 10
    keys = [frozenset(p.player for p in lu.players) for lu in top10]
    assert len(keys) == len(set(keys))


def test_build_top10_by_points_returns_empty_when_no_lineup_fits():
    rows = _small_pool()
    assert build_top10_by_points(rows, salary_cap=100, k=10) == []
