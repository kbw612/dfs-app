"""
Scores an uploaded optimizer pool for the Lineup Analyzer.

A lineup's score is a weighted sum of z-scored structural features (see
features.py). Each feature is standardized against a SYNTHETIC FIELD built from
the slate's projected ownership (synthetic_field.py), so a score reads "how much
does this lineup look like a top-0.1% finisher compared with a typical entry on
this slate". default_weights.json holds weights fitted on 2025 main slates
(real top finishers vs. synthetic field); the user can override any of them.

This is a profile score, not a probability of winning. It ignores projections of
player upside; it cannot see injuries or news after the ownership file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.services.lineup_analyzer.features import FEATURE_NAMES, feature_matrix, pool_arrays
from backend.services.lineup_analyzer.history_loader import HistoricalWeek
from backend.services.lineup_analyzer.pool_parser import Cell, lineup_key
from backend.services.lineup_analyzer.upside_env import (
    EXTRA_FEATURE_NAMES,
    ExtraPool,
    build_extra_pool,
    default_extra_weights,
    extra_feature_matrix,
)
from backend.services.lineup_analyzer.synthetic_field import generate_field

_WEIGHTS_PATH = Path(__file__).with_name("default_weights.json")
FIELD_LINEUPS = 100_000
TIERS = [(99.9, "Top 0.1% profile"), (99.0, "Top 1% profile"), (95.0, "Top 5% profile"), (0.0, "Below")]


def default_weights() -> dict[str, float]:
    data = json.loads(_WEIGHTS_PATH.read_text())
    return {**dict(zip(data["features"], data["weights"])), **default_extra_weights()}


ALL_FEATURE_NAMES = FEATURE_NAMES + EXTRA_FEATURE_NAMES


@dataclass
class FieldStats:
    names: list[str]
    mean: np.ndarray
    std: np.ndarray
    field_z: np.ndarray  # (N, F)
    field_w: np.ndarray  # (N,)
    extra: ExtraPool


_CACHE: dict[str, FieldStats] = {}


def _slate_key(week: HistoricalWeek, extra_key: str) -> str:
    h = hashlib.sha1(extra_key.encode())
    for n in sorted(week.pool):
        p = week.pool[n]
        h.update(f"{n}|{p.position}|{p.team}|{p.salary}|{p.actual_pct:.3f}".encode())
    return h.hexdigest()


def field_stats(week: HistoricalWeek, projections_csv: str | None = None, lines: dict | None = None) -> FieldStats:
    lines = lines or {}
    key = _slate_key(week, f"{projections_csv or ''}|{sorted(lines.items())}")
    if key not in _CACHE:
        field = generate_field(week, n_lineups=FIELD_LINEUPS)
        pool = pool_arrays(week, field.players, "actual")  # live pool: ownership already in actual_pct
        extra = build_extra_pool(week, field.players, projections_csv, lines)
        x = np.hstack([feature_matrix(field.lineups, pool), extra_feature_matrix(field.lineups, extra)])
        w = field.weights
        mean = (x * w[:, None]).sum(axis=0)
        std = np.sqrt(np.maximum(((x - mean) ** 2 * w[:, None]).sum(axis=0), 1e-12))
        _CACHE.clear()
        _CACHE[key] = FieldStats(field.players, mean, std, (x - mean) / std, w, extra)
    return _CACHE[key]


@dataclass
class ScoredPool:
    lineups: list[list[Cell]]  # resolved, canonical names/ids, slot order
    index: np.ndarray  # (L, 9) pool indices
    x: np.ndarray  # raw features
    z: np.ndarray
    unresolved: int


def resolve_pool(raw: list[list[Cell]], week: HistoricalWeek, id_to_name: dict[str, str], names: list[str]) -> ScoredPool:
    index_of = {n: i for i, n in enumerate(names)}
    kept, rows = [], []
    unresolved = 0
    for lineup in raw:
        idx, cells, ok = [], [], True
        for name, pid in lineup:
            canon = id_to_name.get(pid) or name.strip()
            if canon not in index_of:  # DST fallback: lineup text may say "Las Vegas Raiders"
                canon = next((n for n in names if week.pool[n].position == "DST" and (name.strip().endswith(n) or n.endswith(name.strip()))), canon)
            if canon not in index_of:
                ok = False
                break
            idx.append(index_of[canon])
            cells.append((canon, week.pool[canon].dk_id or pid))
        if ok and len(set(idx)) == 9:
            kept.append(cells)
            rows.append(idx)
        else:
            unresolved += 1
    return ScoredPool(kept, np.array(rows, dtype=np.int32).reshape(-1, 9), np.zeros((0, 0)), np.zeros((0, 0)), unresolved)


def featurize(sp: ScoredPool, week: HistoricalWeek, stats: FieldStats) -> ScoredPool:
    pool = pool_arrays(week, stats.names, "actual")
    sp.x = (
        np.hstack([feature_matrix(sp.index, pool), extra_feature_matrix(sp.index, stats.extra)])
        if len(sp.index)
        else np.zeros((0, len(ALL_FEATURE_NAMES)))
    )
    sp.z = (sp.x - stats.mean) / stats.std
    return sp


def score(sp: ScoredPool, stats: FieldStats, weights: dict[str, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(scores, field percentile 0-100, contributions (L, F))."""
    w = np.array([weights.get(n, 0.0) for n in ALL_FEATURE_NAMES])
    contrib = sp.z * w
    scores = contrib.sum(axis=1)
    field_scores = stats.field_z @ w
    order = np.argsort(field_scores)
    cum = np.cumsum(stats.field_w[order])
    pos = np.searchsorted(field_scores[order], scores, side="left")
    below = np.where(pos > 0, cum[np.minimum(pos, len(cum)) - 1], 0.0)
    below = np.where(pos >= len(cum), 1.0, below)
    return scores, below * 100.0, contrib


def tier(percentile: float) -> str:
    return next(label for cut, label in TIERS if percentile >= cut)


def build_portfolio(
    index: np.ndarray, order: np.ndarray, size: int, max_exposure_pct: float, max_overlap: int
) -> list[int]:
    """Greedy: walk lineups best-first; keep one if no player would exceed
    `max_exposure_pct` of `size` and it shares at most `max_overlap` players
    with every lineup already kept."""
    cap = max(1, int(np.floor(size * max_exposure_pct / 100.0 + 1e-9)))
    counts: dict[int, int] = {}
    chosen: list[int] = []
    sets: list[set[int]] = []
    for i in order:
        s = set(int(p) for p in index[i])
        if any(counts.get(p, 0) >= cap for p in s):
            continue
        if any(len(s & t) > max_overlap for t in sets):
            continue
        chosen.append(int(i))
        sets.append(s)
        for p in s:
            counts[p] = counts.get(p, 0) + 1
        if len(chosen) >= size:
            break
    return chosen


__all__ = ["lineup_key"]
