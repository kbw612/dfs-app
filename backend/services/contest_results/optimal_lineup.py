"""
Optimal Lineup -- given a week's already-computed ContestResultRow list
(see contest_results_engine.py's build_contest_result_rows -- one row per
player with their true position, salary, and actual FPTS for the week),
finds the single highest-scoring, salary-cap-legal DraftKings Classic
lineup (1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX [RB/WR/TE], 1 DST) achievable
under a given salary cap.

Only players who have BOTH a salary and a true position are eligible --
a player whose name didn't match anything in the week's DK salary file
can't be legally rostered (there's no known cost to build a real roster
around them). Because ContestResultRow itself only covers players who
were rostered by at least one contest entry (DK's own contest export
never reports actual stats for a player nobody drafted at all), this is
"the best lineup among players someone actually used" rather than a
true whole-slate optimum over every salaried player -- in practice this
is close to the same thing for a large-field "Classic Main" contest
(hundreds of entries collectively draft nearly the entire salary pool),
but it IS a real gap worth knowing about: a min-priced player nobody
drafted who quietly scored well would be invisible here.

Solved as an exact (not heuristic/greedy) combinatorial search, not an
external ILP library (this codebase has none, deliberately -- see
requirements.txt): DK salaries are always issued in whole $100
increments (confirmed against real exports), so salary is tracked in
"salary units" of $100 -- shrinking the search space enough (a 50000
cap -> 500 units) to make an exact per-position dynamic program +
convolution tractable in pure Python. FLEX is handled by trying all 3
ways it could be filled (an extra RB, WR, or TE on top of the 2 RB / 3
WR / 1 TE base) and keeping whichever of the 3 scores highest overall.
"""

from __future__ import annotations

from backend.schemas.contest_results.contest_results import ContestResultRow, OptimalLineup, OptimalLineupPlayer

# DK salaries are always whole $100 increments -- see this module's own
# docstring. Tracking salary in these units (instead of raw dollars)
# shrinks a $50,000 cap down to 500 discrete steps, which is what makes
# an exact (not heuristic) search tractable in pure Python.
SALARY_UNIT = 100

# Base roster requirement before FLEX (DK Classic: 1 QB, 2 RB, 3 WR, 1
# TE, 1 DST -- 8 of the 9 total slots).
_BASE_COUNTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}

# The 3 ways DK Classic's single RB/WR/TE FLEX slot could be filled --
# each is _BASE_COUNTS with exactly one of RB/WR/TE incremented by 1.
_FLEX_SCENARIOS = [
    {"QB": 1, "RB": 3, "WR": 3, "TE": 1, "DST": 1},
    {"QB": 1, "RB": 2, "WR": 4, "TE": 1, "DST": 1},
    {"QB": 1, "RB": 2, "WR": 3, "TE": 2, "DST": 1},
]

# DK's own on-screen roster order.
_POSITION_ORDER = ["QB", "RB", "WR", "TE", "DST"]
_SLOT_DISPLAY_PRIORITY = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "FLEX": 4, "DST": 5}

_NEG_INF = float("-inf")


def _eligible_players_by_position(
    rows: list[ContestResultRow], excluded: frozenset[str] = frozenset()
) -> dict[str, list[ContestResultRow]]:
    """Only rows with both a real salary and a real true position can be
    legally rostered -- see this module's own docstring. `excluded` (by
    player name) additionally drops anyone this particular solve isn't
    allowed to use -- see solve_lineup's own docstring for why."""
    by_position: dict[str, list[ContestResultRow]] = {}
    for row in rows:
        if row.salary is None or row.position is None or row.player in excluded:
            continue
        by_position.setdefault(row.position, []).append(row)
    return by_position


def _knapsack_tables(
    players: list[ContestResultRow], max_count: int, cap_units: int
) -> tuple[list[list[float]], list[list[list[float]]]]:
    """Standard 0/1 knapsack with an extra "exactly c items" dimension:
    dp[c][s] = max total FPTS choosing EXACTLY c of `players` with
    combined cost EXACTLY s salary-units (-inf where no such selection
    exists), for every 0<=c<=max_count and 0<=s<=cap_units.

    `snapshots[i]` is a full copy of dp as it stood after considering the
    first i players -- kept around (one full copy per player, not just
    the running total) purely so _reconstruct can later replay which
    specific players landed in a given winning (c, s) cell; a normal
    knapsack only needs the running table, but recovering the actual
    lineup -- not just its total value -- needs this history."""
    dp = [[_NEG_INF] * (cap_units + 1) for _ in range(max_count + 1)]
    dp[0][0] = 0.0
    snapshots = [[row[:] for row in dp]]
    for player in players:
        cost = player.salary // SALARY_UNIT  # type: ignore[operator]  # salary checked non-None by caller
        fpts = player.fpts
        new_dp = [row[:] for row in dp]
        for c in range(max_count):
            dp_c = dp[c]
            new_dp_c1 = new_dp[c + 1]
            for s in range(cap_units + 1 - cost):
                value = dp_c[s]
                if value == _NEG_INF:
                    continue
                candidate = value + fpts
                ns = s + cost
                if candidate > new_dp_c1[ns]:
                    new_dp_c1[ns] = candidate
        dp = new_dp
        snapshots.append([row[:] for row in dp])
    return dp, snapshots


def _reconstruct(
    players: list[ContestResultRow], snapshots: list[list[list[float]]], count: int, cost_units: int
) -> list[ContestResultRow]:
    """Walks `snapshots` (see _knapsack_tables) backwards from the last
    player to the first, recovering which specific players were chosen
    to reach dp[count][cost_units]."""
    chosen: list[ContestResultRow] = []
    c, s = count, cost_units
    for i in range(len(players), 0, -1):
        if c == 0:
            break
        player = players[i - 1]
        cost = player.salary // SALARY_UNIT  # type: ignore[operator]
        prev = snapshots[i - 1]
        cur = snapshots[i]
        if s >= cost and prev[c - 1][s - cost] != _NEG_INF and prev[c - 1][s - cost] + player.fpts == cur[c][s]:
            chosen.append(player)
            c -= 1
            s -= cost
    return chosen


def _combine(vectors: list[list[float]], cap_units: int) -> tuple[list[float], list[list[int]]]:
    """Sequentially merges the 5 position groups' own `dp[count]` vectors
    (each indexed by exact salary-units spent, see _knapsack_tables) into
    ONE vector indexed by exact TOTAL salary-units spent across every
    group, summing FPTS additively. Returns the merged vector plus, for
    each merge step, which cost the newly-merged-in vector used at every
    resulting total -- so the split back into each group's own cost can
    be replayed afterward (see _solve_scenario)."""
    merged = vectors[0][:]
    splits: list[list[int]] = []
    for vec in vectors[1:]:
        new_merged = [_NEG_INF] * (cap_units + 1)
        choice = [0] * (cap_units + 1)
        for s1, v1 in enumerate(merged):
            if v1 == _NEG_INF:
                continue
            for s2, v2 in enumerate(vec[: cap_units - s1 + 1]):
                if v2 == _NEG_INF:
                    continue
                total = v1 + v2
                ts = s1 + s2
                if total > new_merged[ts]:
                    new_merged[ts] = total
                    choice[ts] = s2
        merged = new_merged
        splits.append(choice)
    return merged, splits


def _solve_scenario(
    pools: dict[str, list[ContestResultRow]], counts: dict[str, int], cap_units: int
) -> tuple[float, list[ContestResultRow]] | None:
    """The best lineup for one specific FLEX assignment (`counts` is one
    entry of _FLEX_SCENARIOS) -- None if this contest's eligible pool
    doesn't even have enough players at some position, or if every
    combination that fills all 5 groups busts the cap."""
    tables: dict[str, list[float]] = {}
    snapshots: dict[str, list[list[list[float]]]] = {}
    for pos in _POSITION_ORDER:
        players = pools.get(pos, [])
        needed = counts[pos]
        if len(players) < needed:
            return None
        dp, snaps = _knapsack_tables(players, needed, cap_units)
        tables[pos] = dp[needed]
        snapshots[pos] = snaps

    vectors = [tables[pos] for pos in _POSITION_ORDER]
    merged, splits = _combine(vectors, cap_units)

    best_cost = max(range(cap_units + 1), key=lambda s: merged[s])
    if merged[best_cost] == _NEG_INF:
        return None

    # Replay the merge splits in reverse to recover each group's own
    # individual salary-unit spend at the winning total.
    costs = [0] * len(_POSITION_ORDER)
    remaining = best_cost
    for i in range(len(_POSITION_ORDER) - 1, 0, -1):
        used = splits[i - 1][remaining]
        costs[i] = used
        remaining -= used
    costs[0] = remaining

    lineup_rows: list[ContestResultRow] = []
    for pos, cost in zip(_POSITION_ORDER, costs):
        lineup_rows.extend(_reconstruct(pools[pos], snapshots[pos], counts[pos], cost))

    return merged[best_cost], lineup_rows


def _assign_display_slots(lineup_rows: list[ContestResultRow]) -> list[OptimalLineupPlayer]:
    """Labels every chosen player with their DK roster slot -- their true
    `position` unless their position group has more players than
    _BASE_COUNTS needs, in which case the extra one (lowest-salary within
    that group, an arbitrary but stable tie-break) is FLEX. Returned in
    DK's own canonical on-screen order (QB, RB, RB, WR, WR, WR, TE,
    FLEX, DST)."""
    by_position: dict[str, list[ContestResultRow]] = {}
    for row in lineup_rows:
        by_position.setdefault(row.position, []).append(row)  # type: ignore[arg-type]
    for group in by_position.values():
        group.sort(key=lambda r: r.salary, reverse=True)  # type: ignore[arg-type,return-value]

    slotted: list[tuple[str, ContestResultRow]] = []
    for pos in _POSITION_ORDER:
        for idx, row in enumerate(by_position.get(pos, [])):
            roster_position = "FLEX" if idx >= _BASE_COUNTS[pos] else pos
            slotted.append((roster_position, row))

    slotted.sort(key=lambda pair: _SLOT_DISPLAY_PRIORITY[pair[0]])
    return [
        OptimalLineupPlayer(
            roster_position=roster_position,
            player=row.player,
            position=row.position,  # type: ignore[arg-type]
            salary=row.salary,  # type: ignore[arg-type]
            fpts=row.fpts,
        )
        for roster_position, row in slotted
    ]


def _solve_core(
    rows: list[ContestResultRow], cap_units: int, excluded: frozenset[str], required: frozenset[str]
) -> tuple[float, list[ContestResultRow]] | None:
    """The constraint-aware heart of this module -- the single best
    lineup (as a raw (total_fpts, chosen_rows) pair, not yet the display-
    ready OptimalLineup) that:
      - never uses anyone in `excluded`
      - uses EVERYONE in `required` (locked in, spending their own salary
        and reducing their position group's remaining need by one each)
    both on top of the usual salary-cap-and-roster-legality constraints.
    `required` players are simply removed from the pool being optimized
    over and their cost/value folded in up front -- the remaining budget
    and remaining per-position counts (still split 3 ways for FLEX, same
    as the unconstrained solve) are then optimized exactly as before.

    Excluded/required constraints are what let backend/services/
    contest_results/lineup_generators.py build an exact top-K of
    DISTINCT lineups (Lawler's method: partition the solution space
    around a found lineup using exactly this kind of constraint) and a
    diversified lineup pool, by repeatedly re-solving with different
    constraints rather than needing a second, different algorithm.
    Returns None if `required` itself isn't fully satisfiable (a
    required player got excluded, doesn't exist, or busts the cap /
    position counts on their own)."""
    pools = _eligible_players_by_position(rows, excluded)
    name_to_row = {row.player: row for players in pools.values() for row in players}

    required_rows: list[ContestResultRow] = []
    for name in required:
        row = name_to_row.get(name)
        if row is None:
            return None
        required_rows.append(row)

    forced_cost_units = sum(row.salary // SALARY_UNIT for row in required_rows)  # type: ignore[operator]
    forced_value = sum(row.fpts for row in required_rows)
    remaining_cap_units = cap_units - forced_cost_units
    if remaining_cap_units < 0:
        return None

    required_names = {row.player for row in required_rows}
    remaining_pools = {
        pos: [row for row in players if row.player not in required_names] for pos, players in pools.items()
    }
    required_by_position: dict[str, list[ContestResultRow]] = {}
    for row in required_rows:
        required_by_position.setdefault(row.position, []).append(row)  # type: ignore[arg-type]

    best: tuple[float, list[ContestResultRow]] | None = None
    for scenario in _FLEX_SCENARIOS:
        needed: dict[str, int] = {}
        scenario_feasible = True
        for pos in _POSITION_ORDER:
            remaining_needed = scenario[pos] - len(required_by_position.get(pos, []))
            if remaining_needed < 0:
                # This scenario's own count for `pos` is already exceeded
                # by required picks alone -- e.g. 2 RBs required but this
                # scenario only has room for 2 total (no RB flex here).
                scenario_feasible = False
                break
            needed[pos] = remaining_needed
        if not scenario_feasible:
            continue

        result = _solve_scenario(remaining_pools, needed, remaining_cap_units)
        if result is None:
            continue
        value, extra_rows = result
        total_value = value + forced_value
        if best is None or total_value > best[0]:
            best = (total_value, required_rows + extra_rows)

    return best


def _finalize_lineup(lineup_rows: list[ContestResultRow], salary_cap: int) -> OptimalLineup:
    players = _assign_display_slots(lineup_rows)
    total_salary = sum(p.salary for p in players)
    total_fpts = sum(p.fpts for p in players)
    return OptimalLineup(
        players=players,
        total_salary=total_salary,
        total_fpts=total_fpts,
        salary_leftover=salary_cap - total_salary,
    )


def solve_lineup(
    rows: list[ContestResultRow],
    salary_cap: int = 50000,
    excluded: frozenset[str] = frozenset(),
    required: frozenset[str] = frozenset(),
) -> OptimalLineup | None:
    """The single highest actual-FPTS-scoring DK Classic lineup (1 QB, 2
    RB, 3 WR, 1 TE, 1 RB/WR/TE FLEX, 1 DST) buildable under `salary_cap`
    from this week's ContestResultRow list, optionally forbidden from
    using anyone in `excluded` and/or required to use everyone in
    `required` (both by player name -- see _solve_core's own docstring
    for why lineup_generators.py needs these). See this module's own
    docstring for the eligible-player pool and its coverage caveat. Tries
    all 3 ways FLEX could be filled (_FLEX_SCENARIOS) and returns
    whichever scores highest; None if no legal 9-player roster satisfying
    every constraint fits under the cap at all."""
    if salary_cap % SALARY_UNIT != 0:
        # DK salaries are always $100 increments (see module docstring) --
        # round the cap down so it's never treated as more forgiving than
        # it really is.
        salary_cap -= salary_cap % SALARY_UNIT
    cap_units = salary_cap // SALARY_UNIT

    result = _solve_core(rows, cap_units, excluded, required)
    if result is None:
        return None

    _total_value, lineup_rows = result
    return _finalize_lineup(lineup_rows, salary_cap)


def build_optimal_lineup(rows: list[ContestResultRow], salary_cap: int = 50000) -> OptimalLineup | None:
    """Backward-compatible unconstrained entry point -- see solve_lineup,
    which this is now a thin wrapper over (excluded/required both empty)."""
    return solve_lineup(rows, salary_cap)
