"""
Per-lineup factor features for the Lineup Analyzer -- the numbers a lineup is
scored on. Every feature is structural (ownership, salary shape, stacking);
none uses a player's realized points, so the same features can be computed
for a live slate before kickoff.

Lineups are (N, 9) integer matrices of pool-player indices in the synthetic
field's slot order -- QB, RB, RB, WR, WR, WR, TE, FLEX, DST (see
synthetic_field.py) -- so the same code scores a synthetic field, a week's
real top finishers, or an uploaded optimizer pool.

Ownership used for scoring is `scoring_ownership`: the pre-game projection
where one exists for the player, else (for a player the projection file left
out) the lowest projected value that week -- the file lists only the ~110-170
most relevant players, so anyone missing is lower than all of them -- and the
contest's actual %Drafted only in "actual" mode / for weeks with no projection
file at all (marked optimistic by the caller).

Features (names in FEATURE_NAMES):

- own_sum: total ownership of the 9 players (%).
- log_own_prod: sum of log10(ownership/100) -- a duplication proxy; more
  negative means a rarer combination of players.
- max_own: the single most-owned player.
- n_chalk / n_low: players at or above CHALK_PCT, at or below LOW_PCT.
- qb_own: the QB's ownership.
- unused_k: unused salary, in $1,000s.
- n_stars / n_punts: skill players priced at or above STAR_SALARY / at or
  below PUNT_SALARY.
- qb_mates: QB teammates among the 7 RB/WR/TE slots, capped at 3.
- bringback: 1 when an opposing-team RB/WR/TE is rostered with the QB.
- game_stack: most QB/RB/WR/TE players from one game (both teams count).
- dst_conflict: offensive players facing the lineup's own DST (their
  points work against it).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.services.lineup_analyzer.history_loader import HistoricalWeek

SALARY_CAP = 50000
CHALK_PCT = 20.0
LOW_PCT = 3.0
STAR_SALARY = 8000
PUNT_SALARY = 4500
_MIN_OWN_FOR_LOG = 0.1  # floor so a 0% player doesn't send the log to -inf

FEATURE_NAMES = [
    "own_sum",
    "log_own_prod",
    "max_own",
    "n_chalk",
    "n_low",
    "qb_own",
    "unused_k",
    "n_stars",
    "n_punts",
    "qb_mates",
    "bringback",
    "game_stack",
    "dst_conflict",
]


@dataclass
class PoolArrays:
    """A week's pool as parallel arrays, indexed like SyntheticField.players
    (sorted names)."""

    names: list[str]
    ownership: np.ndarray  # scoring ownership, %
    salary: np.ndarray
    team: np.ndarray  # team code
    opponent: np.ndarray  # opponent's team code, -1 if unknown
    game: np.ndarray  # game id shared by both teams, -1 if unknown
    is_skill: np.ndarray  # RB/WR/TE


def scoring_ownership(week: HistoricalWeek, mode: str = "projected") -> dict[str, float]:
    """{player: ownership % to score with}. mode "actual" uses the contest's
    own %Drafted; "projected" uses the pre-game projection where the week has
    one (see the module docstring for players it leaves out)."""
    if mode == "actual" or not week.has_projections:
        return {name: p.actual_pct for name, p in week.pool.items()}
    projected = [p.projected_pct for p in week.pool.values() if p.projected_pct is not None]
    default = min(projected) if projected else 0.0
    return {name: (p.projected_pct if p.projected_pct is not None else default) for name, p in week.pool.items()}


def pool_arrays(week: HistoricalWeek, names: list[str], mode: str = "projected") -> PoolArrays:
    own = scoring_ownership(week, mode)
    teams = sorted({p.team for p in week.pool.values()} | {p.opponent for p in week.pool.values() if p.opponent})
    code = {team: i for i, team in enumerate(teams)}
    games: dict[tuple[int, int], int] = {}
    game_ids = []
    opp_codes = []
    for name in names:
        p = week.pool[name]
        opp = code.get(p.opponent, -1) if p.opponent else -1
        opp_codes.append(opp)
        if opp < 0:
            game_ids.append(-1)
        else:
            key = (min(code[p.team], opp), max(code[p.team], opp))
            game_ids.append(games.setdefault(key, len(games)))
    return PoolArrays(
        names=names,
        ownership=np.array([own[n] for n in names], dtype=np.float64),
        salary=np.array([week.pool[n].salary for n in names], dtype=np.int64),
        team=np.array([code[week.pool[n].team] for n in names], dtype=np.int32),
        opponent=np.array(opp_codes, dtype=np.int32),
        game=np.array(game_ids, dtype=np.int32),
        is_skill=np.array([week.pool[n].position in ("RB", "WR", "TE") for n in names]),
    )


def feature_matrix(lineups: np.ndarray, pool: PoolArrays) -> np.ndarray:
    """(N, len(FEATURE_NAMES)) float matrix for N lineups."""
    own = pool.ownership[lineups]
    salary = pool.salary[lineups]
    qb, dst = lineups[:, 0], lineups[:, 8]
    skill = lineups[:, 1:8]

    qb_team = pool.team[qb]
    mates = ((pool.team[skill] == qb_team[:, None])).sum(axis=1)
    bringback = ((pool.team[skill] == pool.opponent[qb][:, None]) & (pool.opponent[qb][:, None] >= 0)).any(axis=1)

    offense = lineups[:, :8]
    game_ids = pool.game[offense]
    game_stack = np.zeros(len(lineups))
    for g in np.unique(game_ids[game_ids >= 0]):
        game_stack = np.maximum(game_stack, (game_ids == g).sum(axis=1))

    dst_opp = pool.opponent[dst]
    dst_conflict = ((pool.team[offense] == dst_opp[:, None]) & (dst_opp[:, None] >= 0)).sum(axis=1)

    skill_salary = salary[:, 1:8]
    features = np.column_stack(
        [
            own.sum(axis=1),
            np.log10(np.maximum(own, _MIN_OWN_FOR_LOG) / 100.0).sum(axis=1),
            own.max(axis=1),
            (own >= CHALK_PCT).sum(axis=1),
            (own <= LOW_PCT).sum(axis=1),
            own[:, 0],
            (SALARY_CAP - salary.sum(axis=1)) / 1000.0,
            (skill_salary >= STAR_SALARY).sum(axis=1),
            (skill_salary <= PUNT_SALARY).sum(axis=1),
            np.minimum(mates, 3),
            bringback.astype(float),
            game_stack,
            dst_conflict,
        ]
    )
    return features.astype(np.float64)


def lineup_index_matrix(lineups_players: list[list[str]], names: list[str]) -> np.ndarray:
    """Names in slot order -> (N, 9) index matrix, for real lineups."""
    index = {name: i for i, name in enumerate(names)}
    return np.array([[index[n] for n in row] for row in lineups_players], dtype=np.int32)


def slot_ordered_names(slots: list[tuple[str, str, str]]) -> list[str]:
    """[(slot, position, name)] from a real lineup -> names in the synthetic
    slot order QB, RB, RB, WR, WR, WR, TE, FLEX, DST. The FLEX player's real
    position decides nothing here (the features only separate QB, DST and
    "the 7 skill slots")."""
    by_slot: dict[str, list[str]] = {}
    for slot, _position, name in slots:
        by_slot.setdefault(slot, []).append(name)
    ordered = (
        by_slot["QB"]
        + by_slot["RB"]
        + by_slot["WR"]
        + by_slot["TE"]
        + by_slot.get("FLEX", [])
        + by_slot["DST"]
    )
    return ordered
