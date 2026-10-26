"""
A synthetic stand-in for the field of a past main-slate GPP -- the "everyone
else" that real top finishers are compared against. The standings files only
hold the top ~0.1% of a 317,000-entry contest, so there are no actual losing
lineups to learn from; this module generates plausible ones instead.

How a synthetic lineup is built (DK Classic: 1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX,
1 DST, $50,000 cap):

1. Each player gets a sampling weight, starting at his actual %Drafted in
   the main contest (history_loader.HistoricalPlayer.actual_pct).
2. Players are drawn without replacement per position (Gumbel top-k, so the
   draw is vectorized). The FLEX position is drawn from the contest's own
   numbers: position ownership totals minus the 200/300/100 points the
   fixed slots account for gives the RB/WR/TE FLEX shares (e.g. RB 233% =
   200% for the two RB slots + 33% of lineups with an RB FLEX).
3. Each lineup carries an importance weight instead of being thrown away:
   0 if over the cap, otherwise exp(-unused_penalty * unused_salary/$1,000)
   * exp(stack_boost * QB teammates), because real entrants use nearly all
   their salary and stack their QB far more often than independent sampling
   would. Both are tunable (see calibrate_field_parameters).
4. Player weights are re-fit a few rounds (iterative proportional fitting) so
   that the WEIGHTED share of lineups containing each player matches his
   actual %Drafted -- the field's player exposure is right by construction,
   whatever the two knobs above do to lineup shape.

Points come from each player's actual FPTS in that contest, so a synthetic
lineup's score is the score it really would have had. The field's points
distribution then gives: the score of the Nth-best of 317,000 entries (to
check the field against the real top-finisher file) and the top-1% cutoff the
files don't contain.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.services.lineup_analyzer.history_loader import HistoricalWeek

SALARY_CAP = 50000
# Roster slot order in the stored lineup matrix: QB, RB, RB, WR, WR, WR, TE,
# FLEX, DST. (FLEX is whichever RB/WR/TE extra player the draw produced.)
SLOT_COUNT = 9
POSITIONS = ("QB", "RB", "WR", "TE", "DST")
_FIXED_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
# Per-position totals the fixed slots account for, in % of lineups.
_FIXED_PCT = {"QB": 100.0, "RB": 200.0, "WR": 300.0, "TE": 100.0, "DST": 100.0}
_CHUNK = 20000
_EPS_WEIGHT = 1e-9


@dataclass(frozen=True)
class FieldParams:
    """The two lineup-shape knobs (see the module docstring). The defaults
    come from a grid over 2025 weeks 2-18 (penalty 0.5-3.0, boost 0-1.0): the
    field's score at the top-file fraction was within about 5 points of the
    real file's lowest score in 14 of 17 weeks for every pair, and the pairs
    barely differ, so a middle setting is used. Weeks 11 (only 222 rows; its
    contest looks smaller) and 18 are the outliers."""

    unused_penalty: float = 1.5
    stack_boost: float = 0.5


@dataclass
class SyntheticField:
    week: int
    players: list[str]  # pool player names, index = id used in `lineups`
    lineups: np.ndarray  # (N, 9) int32 indices into `players`
    weights: np.ndarray  # (N,) importance weights, sum to 1
    points: np.ndarray  # (N,) actual points each lineup would have scored
    salary: np.ndarray  # (N,)
    qb_teammates: np.ndarray  # (N,) skill players sharing the QB's team

    def cutoff_points(self, fraction: float) -> float:
        """Points of the lineup at the top `fraction` of the field (e.g.
        0.01 = the top-1% cutoff), by cumulative importance weight."""
        order = np.argsort(-self.points)
        cumulative = np.cumsum(self.weights[order])
        index = int(np.searchsorted(cumulative, fraction))
        return float(self.points[order[min(index, len(order) - 1)]])


class _PositionPool:
    """Pool players of one position as parallel arrays."""

    def __init__(self, indices: list[int], target_pct: np.ndarray) -> None:
        self.indices = np.array(indices, dtype=np.int32)
        self.target_pct = target_pct
        self.weights = np.maximum(target_pct, 0.0)


def _flex_probabilities(week: HistoricalWeek) -> dict[str, float]:
    """P(FLEX is RB / WR / TE), from position ownership totals above what
    the fixed slots need. Falls back to an even RB/WR split with a little TE
    if the totals give nothing usable."""
    totals = {pos: 0.0 for pos in ("RB", "WR", "TE")}
    for player in week.pool.values():
        if player.position in totals:
            totals[player.position] += player.actual_pct
    extra = {pos: max(totals[pos] - _FIXED_PCT[pos], 0.0) for pos in totals}
    total_extra = sum(extra.values())
    if total_extra <= 0:
        return {"RB": 0.45, "WR": 0.45, "TE": 0.10}
    return {pos: value / total_extra for pos, value in extra.items()}


def _gumbel_top_k(weights: np.ndarray, k: int, n: int, rng: np.random.Generator) -> np.ndarray:
    """(n, k) indices into `weights`, drawn without replacement with
    probability roughly proportional to weight (Gumbel-max trick)."""
    log_w = np.log(np.maximum(weights, _EPS_WEIGHT))
    keys = log_w[None, :] + rng.gumbel(size=(n, len(weights)))
    return np.argpartition(-keys, k - 1, axis=1)[:, :k]


def _generate_raw(
    week: HistoricalWeek,
    pools: dict[str, _PositionPool],
    flex_probs: dict[str, float],
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """(n, 9) pool indices, un-weighted and ignoring the salary cap."""
    out = np.empty((n, SLOT_COUNT), dtype=np.int32)
    flex_choice = rng.choice(["RB", "WR", "TE"], size=n, p=[flex_probs["RB"], flex_probs["WR"], flex_probs["TE"]])
    # Slot columns: 0 QB, 1-2 RB, 3-5 WR, 6 TE, 7 FLEX, 8 DST.
    for start in range(0, n, _CHUNK):
        end = min(start + _CHUNK, n)
        size = end - start
        chunk_flex = flex_choice[start:end]
        qb = _gumbel_top_k(pools["QB"].weights, 1, size, rng)
        dst = _gumbel_top_k(pools["DST"].weights, 1, size, rng)
        out[start:end, 0] = pools["QB"].indices[qb[:, 0]]
        out[start:end, 8] = pools["DST"].indices[dst[:, 0]]
        for pos, columns in (("RB", (1, 2)), ("WR", (3, 4, 5)), ("TE", (6,))):
            extra_mask = chunk_flex == pos
            base = len(columns)
            drawn = _gumbel_top_k(pools[pos].weights, base + 1, size, rng)  # one spare for FLEX
            mapped = pools[pos].indices[drawn]
            for offset, column in enumerate(columns):
                out[start:end, column] = mapped[:, offset]
            # The spare draw is the FLEX only for lineups whose FLEX is this position.
            spare = mapped[:, base]
            flex_slot = out[start:end, 7]
            flex_slot[extra_mask] = spare[extra_mask]
    return out


def _importance_weights(
    lineups: np.ndarray,
    salary: np.ndarray,
    team_ids: np.ndarray,
    is_skill: np.ndarray,
    params: FieldParams,
) -> tuple[np.ndarray, np.ndarray]:
    """(importance weight per lineup, QB-teammate count per lineup)."""
    qb_team = team_ids[lineups[:, 0]]
    skill_cols = lineups[:, 1:8]
    mates = ((team_ids[skill_cols] == qb_team[:, None]) & is_skill[skill_cols]).sum(axis=1)
    unused = SALARY_CAP - salary
    weight = np.where(unused >= 0, np.exp(-params.unused_penalty * unused / 1000.0), 0.0)
    weight = weight * np.exp(params.stack_boost * np.minimum(mates, 3))
    # A lineup with a duplicate player (the FLEX draw can't clash with its own
    # position's top-k by construction, but be safe) gets no weight.
    sorted_lineups = np.sort(lineups, axis=1)
    duplicate = (sorted_lineups[:, 1:] == sorted_lineups[:, :-1]).any(axis=1)
    weight = np.where(duplicate, 0.0, weight)
    return weight, mates


def generate_field(
    week: HistoricalWeek,
    params: FieldParams | None = None,
    n_lineups: int = 200_000,
    seed: int = 7,
    fit_rounds: int = 6,
    fit_sample: int = 60_000,
) -> SyntheticField:
    """Builds and returns one week's synthetic field. Raises ValueError if the
    pool lacks players for a roster position."""
    params = params or FieldParams()
    rng = np.random.default_rng(seed)

    names = sorted(week.pool)
    index_of = {name: i for i, name in enumerate(names)}
    players = [week.pool[name] for name in names]
    salary_all = np.array([p.salary for p in players], dtype=np.int64)
    fpts_all = np.array([p.fpts or 0.0 for p in players], dtype=np.float64)
    target_all = np.array([p.actual_pct for p in players], dtype=np.float64)
    team_codes = {team: i for i, team in enumerate(sorted({p.team for p in players}))}
    team_ids = np.array([team_codes[p.team] for p in players], dtype=np.int32)
    is_skill = np.array([p.position in ("RB", "WR", "TE") for p in players])

    pools: dict[str, _PositionPool] = {}
    for pos in POSITIONS:
        idx = [index_of[p.name] for p in players if p.position == pos and p.actual_pct > 0]
        if len(idx) < _FIXED_SLOTS[pos] + 1:
            raise ValueError(f"week {week.week}: not enough drafted {pos} players ({len(idx)}) to sample lineups")
        pools[pos] = _PositionPool(idx, target_all[idx])
    flex_probs = _flex_probabilities(week)

    # Iterative proportional fitting of the player sampling weights: nudge
    # each player's weight by target / achieved weighted exposure.
    for _ in range(fit_rounds):
        lineups = _generate_raw(week, pools, flex_probs, fit_sample, rng)
        salary = salary_all[lineups].sum(axis=1)
        weight, _mates = _importance_weights(lineups, salary, team_ids, is_skill, params)
        total = weight.sum()
        if total <= 0:
            raise ValueError(f"week {week.week}: no synthetic lineup fit under the salary cap")
        exposure = np.zeros(len(players))
        flat = lineups.reshape(-1)
        np.add.at(exposure, flat, np.repeat(weight, SLOT_COUNT))
        exposure = exposure / total * 100.0
        for pos in POSITIONS:
            pool = pools[pos]
            achieved = exposure[pool.indices]
            ratio = np.where(achieved > 0, pool.target_pct / np.maximum(achieved, 1e-6), 1.5)
            pool.weights = pool.weights * np.clip(ratio, 0.25, 4.0)

    lineups = _generate_raw(week, pools, flex_probs, n_lineups, rng)
    salary = salary_all[lineups].sum(axis=1)
    weight, mates = _importance_weights(lineups, salary, team_ids, is_skill, params)
    total = weight.sum()
    if total <= 0:
        raise ValueError(f"week {week.week}: no synthetic lineup fit under the salary cap")
    weight = weight / total
    points = fpts_all[lineups].sum(axis=1)
    return SyntheticField(week.week, names, lineups, weight, points, salary, mates)


def exposure_error(field: SyntheticField, week: HistoricalWeek) -> float:
    """Mean absolute gap, in percentage points, between the field's weighted
    player exposure and the contest's actual %Drafted over players owned 1%+."""
    exposure = np.zeros(len(field.players))
    np.add.at(exposure, field.lineups.reshape(-1), np.repeat(field.weights, SLOT_COUNT))
    gaps = [
        abs(exposure[i] * 100.0 - week.pool[name].actual_pct)
        for i, name in enumerate(field.players)
        if week.pool[name].actual_pct >= 1.0
    ]
    return float(np.mean(gaps)) if gaps else 0.0


@dataclass
class WeekFit:
    week: int
    entries_in_file: int
    actual_cutoff: float  # lowest score in the real top-finisher file
    synthetic_cutoff: float  # synthetic field's score at the same top fraction
    synthetic_top1pct: float


def evaluate_week(
    week: HistoricalWeek,
    params: FieldParams,
    field_size: int = 317_000,
    n_lineups: int = 60_000,
    seed: int = 7,
) -> WeekFit:
    """Generates the week's field and compares its score at the file's own
    top fraction (entries in the file / field size) with the real file's
    lowest score -- the one point where synthetic and real can be checked
    against each other."""
    field = generate_field(week, params, n_lineups=n_lineups, seed=seed, fit_sample=30_000)
    entries = len(week.lineups)
    fraction = entries / field_size
    return WeekFit(
        week=week.week,
        entries_in_file=entries,
        actual_cutoff=min(lineup.points for lineup in week.lineups),
        synthetic_cutoff=field.cutoff_points(fraction),
        synthetic_top1pct=field.cutoff_points(0.01),
    )


def calibrate_field_parameters(
    weeks: list[HistoricalWeek],
    grid: list[FieldParams],
    field_size: int = 317_000,
) -> list[tuple[FieldParams, float, float, list[WeekFit]]]:
    """For each parameter pair: (params, mean signed error, RMSE, per-week
    fits), where error = synthetic cutoff - actual cutoff in points at the
    top-file fraction. Sorted best (lowest RMSE) first."""
    results = []
    for params in grid:
        fits = [evaluate_week(week, params, field_size) for week in weeks]
        errors = np.array([fit.synthetic_cutoff - fit.actual_cutoff for fit in fits])
        results.append((params, float(errors.mean()), float(np.sqrt((errors**2).mean())), fits))
    results.sort(key=lambda item: item[2])
    return results
