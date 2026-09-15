"""
Generates a POOL of optimal-style lineups (not just the single best one
-- see optimal_lineup.py for that), built on top of that module's
solve_lineup(rows, salary_cap, excluded, required): the same constrained
solver, called repeatedly with different constraints, rather than a
whole separate optimization algorithm.

build_top10_by_points -- the exact top-10 DISTINCT lineups by total
FPTS, via Lawler's classic "rank the k best solutions" method (used for
k-shortest-path/k-best-assignment problems generally): solve once for
the global best, then repeatedly partition the remaining solution space
around whichever lineup was just accepted (fixing it OUT for one branch
per one of its own 9 players, while requiring the others earlier in a
stable order stay IN for that branch -- see _push_branches), re-solving
each partition and keeping the best not-yet-accepted candidate in a
priority queue. This is exact -- the 10 lineups really are the 10
highest-scoring distinct rosters possible -- but because it's a true
ranking of ALL possible lineups, consecutive entries are often nearly
identical (lineup #2 might swap out just one bench-level FLEX for
another).
"""

from __future__ import annotations

import heapq
import itertools

from backend.schemas.contest_results.contest_results import ContestResultRow, OptimalLineup
from backend.services.contest_results.optimal_lineup import solve_lineup

DEFAULT_LINEUP_COUNT = 10


def _lineup_key(lineup: OptimalLineup) -> frozenset[str]:
    """A lineup's identity for dedup purposes -- WHO is on it, not which
    roster slot they occupy (two lineups with the same 9 players are the
    same lineup even if FLEX display-labeling differs, which can't
    actually happen given _assign_display_slots's own deterministic
    tie-break, but this is the correct notion of "distinct" regardless)."""
    return frozenset(p.player for p in lineup.players)


def build_top10_by_points(
    rows: list[ContestResultRow], salary_cap: int = 50000, k: int = DEFAULT_LINEUP_COUNT
) -> list[OptimalLineup]:
    """The exact top-`k` DISTINCT lineups by total FPTS -- see this
    module's own docstring for the Lawler's-method algorithm. Returns
    fewer than `k` if there simply aren't that many distinct legal
    lineups under this cap (a thin eligible pool)."""
    first = solve_lineup(rows, salary_cap)
    if first is None:
        return []

    lineups: list[OptimalLineup] = [first]
    seen_keys: set[frozenset[str]] = {_lineup_key(first)}

    # Min-heap of (-total_fpts, tiebreak_counter, candidate, excluded, required)
    # -- negated value turns Python's min-heap into the max-heap we want
    # ("pop the next-best candidate"). `tiebreak_counter` is unique per
    # push so heapq never has to compare two OptimalLineup objects
    # directly (they're not orderable) when values tie.
    heap: list[tuple[float, int, OptimalLineup, frozenset[str], frozenset[str]]] = []
    counter = itertools.count()

    def push_branches(source: OptimalLineup, excluded: frozenset[str], required: frozenset[str]) -> None:
        """Partitions the solution space NOT containing `source` into one
        branch per player in `source`: branch i excludes that player
        while requiring every earlier player (in `source`'s own fixed
        order) stay included -- together these branches cover every
        possible OTHER lineup exactly once (see this module's own
        docstring), so the best candidate among them is a valid
        next-best-overall candidate."""
        names = [p.player for p in source.players]
        for i, name in enumerate(names):
            branch_excluded = excluded | {name}
            branch_required = required | set(names[:i])
            candidate = solve_lineup(rows, salary_cap, excluded=branch_excluded, required=branch_required)
            if candidate is None:
                continue
            heapq.heappush(heap, (-candidate.total_fpts, next(counter), candidate, branch_excluded, branch_required))

    push_branches(first, frozenset(), frozenset())

    while len(lineups) < k and heap:
        _neg_value, _tiebreak, candidate, excluded, required = heapq.heappop(heap)
        key = _lineup_key(candidate)
        if key in seen_keys:
            # This branch's own optimum happens to duplicate an already-
            # accepted lineup -- still expand ITS branches (a genuine
            # next-best may be hiding behind it), just don't count it
            # twice.
            push_branches(candidate, excluded, required)
            continue
        lineups.append(candidate)
        seen_keys.add(key)
        push_branches(candidate, excluded, required)

    return lineups
