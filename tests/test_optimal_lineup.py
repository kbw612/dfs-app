from itertools import combinations

from backend.schemas.contest_results.contest_results import ContestResultRow
from backend.services.contest_results.optimal_lineup import build_optimal_lineup


def make_row(player, position, salary, fpts, week=1):
    return ContestResultRow(week=week, player=player, salary=salary, position=position, pct_drafted=0.0, fpts=fpts)


def _small_pool():
    # Small but non-trivial pool -- multiple affordable/expensive options
    # at every position so the salary cap actually forces trade-offs.
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


def _brute_force_best_value(rows: list[ContestResultRow], cap: int) -> float:
    """Exhaustively tries every legal DK Classic roster (1 QB, 2-3 RB,
    3-4 WR, 1-2 TE with exactly one RB/WR/TE "extra" for FLEX, 1 DST)
    from `rows` and returns the highest total FPTS achievable at or under
    `cap`. Independent of build_optimal_lineup's own DP implementation --
    used as a ground-truth cross-check, not a reimplementation of it."""
    by_position: dict[str, list[ContestResultRow]] = {}
    for row in rows:
        by_position.setdefault(row.position, []).append(row)

    best = None
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
                                    value = sum(r.fpts for r in group)
                                    if best is None or value > best:
                                        best = value
    return best


def test_build_optimal_lineup_matches_brute_force_optimum():
    rows = _small_pool()
    for cap in (13000, 15000, 17000, 20000):
        lineup = build_optimal_lineup(rows, salary_cap=cap)
        expected = _brute_force_best_value(rows, cap)
        if expected is None:
            assert lineup is None
        else:
            assert lineup is not None
            assert round(lineup.total_fpts, 6) == round(expected, 6)
            assert lineup.total_salary <= cap


def test_build_optimal_lineup_respects_salary_cap():
    rows = _small_pool()
    lineup = build_optimal_lineup(rows, salary_cap=17000)
    assert lineup is not None
    assert lineup.total_salary <= 17000
    assert lineup.salary_leftover == 17000 - lineup.total_salary


def test_build_optimal_lineup_has_legal_roster_composition():
    rows = _small_pool()
    lineup = build_optimal_lineup(rows, salary_cap=20000)
    assert lineup is not None
    assert len(lineup.players) == 9

    by_slot: dict[str, int] = {}
    for p in lineup.players:
        by_slot[p.roster_position] = by_slot.get(p.roster_position, 0) + 1
    assert by_slot.get("QB") == 1
    assert by_slot.get("DST") == 1
    assert by_slot.get("FLEX") == 1
    assert by_slot.get("RB", 0) in (2, 3)
    assert by_slot.get("WR", 0) in (3, 4)
    assert by_slot.get("TE", 0) in (1, 2)

    # FLEX must be a true RB/WR/TE, never QB or DST.
    flex_player = next(p for p in lineup.players if p.roster_position == "FLEX")
    assert flex_player.position in ("RB", "WR", "TE")


def test_build_optimal_lineup_excludes_players_missing_salary_or_position():
    rows = _small_pool() + [
        ContestResultRow(week=1, player="No Salary Guy", salary=None, position="WR", pct_drafted=0.0, fpts=99.0),
        ContestResultRow(week=1, player="No Position Guy", salary=1000, position=None, pct_drafted=0.0, fpts=99.0),
    ]
    lineup = build_optimal_lineup(rows, salary_cap=20000)
    assert lineup is not None
    names = {p.player for p in lineup.players}
    # Despite absurdly high FPTS, neither unmatched player can be legally
    # rostered (no known cost / no known position) so neither appears.
    assert "No Salary Guy" not in names
    assert "No Position Guy" not in names


def test_build_optimal_lineup_returns_none_when_not_enough_players_at_a_position():
    # Only 1 RB total in the whole pool -- DK Classic needs at least 2.
    rows = [
        make_row("QB A", "QB", 5000, 20.0),
        make_row("RB 1", "RB", 5000, 10.0),
        make_row("WR 1", "WR", 5000, 10.0),
        make_row("WR 2", "WR", 5000, 10.0),
        make_row("WR 3", "WR", 5000, 10.0),
        make_row("TE 1", "TE", 5000, 10.0),
        make_row("DST 1", "DST", 5000, 10.0),
    ]
    assert build_optimal_lineup(rows, salary_cap=50000) is None


def test_build_optimal_lineup_returns_none_when_cheapest_roster_busts_cap():
    rows = _small_pool()
    assert build_optimal_lineup(rows, salary_cap=100) is None


def test_build_optimal_lineup_rounds_cap_down_to_nearest_100():
    # DK salaries are always $100 increments -- a cap that isn't one
    # itself should be treated as the next $100 down, never rounded up
    # (never more forgiving than the real cap requested).
    rows = _small_pool()
    lineup_17099 = build_optimal_lineup(rows, salary_cap=17099)
    lineup_17000 = build_optimal_lineup(rows, salary_cap=17000)
    assert lineup_17099 is not None
    assert lineup_17000 is not None
    assert lineup_17099.total_fpts == lineup_17000.total_fpts
    assert lineup_17099.total_salary <= 17000


def test_build_optimal_lineup_real_world_scale_matches_brute_force():
    # A larger, more realistic pool (2 QB, 4 RB, 5 WR, 2 TE, 2 DST) --
    # still small enough for the brute-force cross-check to run quickly,
    # but big enough to exercise real budget trade-offs (an "obviously
    # good value" player isn't always worth it once its salary savings
    # could instead upgrade a different slot -- so this only checks the
    # final achieved total against independent brute force, not specific
    # picks).
    rows = [
        make_row("Elite QB", "QB", 8000, 30.0),
        make_row("Cheap QB", "QB", 4500, 10.0),
        make_row("Elite RB", "RB", 8500, 35.0),
        make_row("Mid RB", "RB", 6000, 20.0),
        make_row("Value RB", "RB", 4000, 22.0),
        make_row("Chalk RB", "RB", 5000, 12.0),
        make_row("Elite WR", "WR", 8200, 33.0),
        make_row("Mid WR", "WR", 6200, 18.0),
        make_row("Value WR", "WR", 4200, 21.0),
        make_row("Chalk WR", "WR", 5200, 13.0),
        make_row("Punt WR", "WR", 3000, 8.0),
        make_row("Elite TE", "TE", 6500, 24.0),
        make_row("Punt TE", "TE", 2500, 6.0),
        make_row("Good DST", "DST", 3000, 15.0),
        make_row("Cheap DST", "DST", 2000, 5.0),
    ]
    lineup = build_optimal_lineup(rows, salary_cap=50000)
    expected = _brute_force_best_value(rows, 50000)
    assert lineup is not None
    assert lineup.total_salary <= 50000
    assert round(lineup.total_fpts, 6) == round(expected, 6)
