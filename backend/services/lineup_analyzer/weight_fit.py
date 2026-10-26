"""
Fits the Lineup Analyzer's factor weights: a regularized logistic regression
that separates a week's REAL top finishers (about the top 0.1% of a 317,000-
entry main slate) from lineups drawn out of that week's SYNTHETIC field (see
synthetic_field.py), using the structural features in features.py.

Each feature is standardized against the week's own field first (weighted
mean/std of the synthetic field), so "own_sum = +1" means "1 std above a typical
entry on THIS slate" and weeks with different ownership levels pool cleanly.
The fitted coefficients are therefore the weights of a z-scored sum, which the
analyzer reproduces on a live slate by standardizing an uploaded pool against
a synthetic field built from that slate's projected ownership.

What the fit can and can't say:

- It learns what top finishers looked like relative to the field, not a causal
  recipe: finishing at the top also rewards luck (a low-owned player hitting).
  Ownership/leverage weights are well grounded because the field's player
  exposure is fit to the contest's real %Drafted; the stacking and unused-
  salary weights depend on the field's two assumed lineup-shape knobs
  (FieldParams), so treat those as relative guidance.
- Held-out weeks (never used to fit) measure whether the score still
  separates top finishers from the field out of sample.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.services.lineup_analyzer.features import (
    FEATURE_NAMES,
    feature_matrix,
    lineup_index_matrix,
    pool_arrays,
    slot_ordered_names,
)
from backend.services.lineup_analyzer.history_loader import HistoricalWeek
from backend.services.lineup_analyzer.synthetic_field import SyntheticField


@dataclass
class WeekData:
    """One week's standardized features: real top lineups and the field."""

    week: int
    real_z: np.ndarray  # (R, F)
    field_z: np.ndarray  # (N, F)
    field_weights: np.ndarray  # (N,), sum to 1


def week_data(week: HistoricalWeek, field: SyntheticField, mode: str = "projected") -> WeekData:
    pool = pool_arrays(week, field.players, mode)
    field_x = feature_matrix(field.lineups, pool)
    w = field.weights
    mean = (field_x * w[:, None]).sum(axis=0)
    var = ((field_x - mean) ** 2 * w[:, None]).sum(axis=0)
    std = np.sqrt(np.maximum(var, 1e-12))
    real_names = [slot_ordered_names([(s, p.position, p.name) for s, p in lineup.players]) for lineup in week.lineups]
    real_x = feature_matrix(lineup_index_matrix(real_names, field.players), pool)
    return WeekData(week.week, (real_x - mean) / std, (field_x - mean) / std, w)


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, iterations: int = 25) -> tuple[np.ndarray, float]:
    """Newton-Raphson logistic regression with an L2 penalty on the weights
    (not the intercept). Returns (weights, intercept)."""
    n, f = x.shape
    design = np.column_stack([x, np.ones(n)])
    beta = np.zeros(f + 1)
    penalty = np.diag([l2] * f + [0.0])
    for _ in range(iterations):
        p = 1.0 / (1.0 + np.exp(-np.clip(design @ beta, -30, 30)))
        gradient = design.T @ (y - p) - penalty @ beta
        hessian = (design * (p * (1 - p))[:, None]).T @ design + penalty + 1e-9 * np.eye(f + 1)
        step = np.linalg.solve(hessian, gradient)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    return beta[:-1], float(beta[-1])


def training_set(
    data: list[WeekData], negatives_per_positive: int = 3, seed: int = 11
) -> tuple[np.ndarray, np.ndarray]:
    """Stacks every week's real lineups (label 1) with field lineups resampled
    by importance weight (label 0)."""
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for d in data:
        n_neg = negatives_per_positive * len(d.real_z)
        picks = rng.choice(len(d.field_z), size=n_neg, p=d.field_weights)
        xs += [d.real_z, d.field_z[picks]]
        ys += [np.ones(len(d.real_z)), np.zeros(n_neg)]
    return np.vstack(xs), np.concatenate(ys)


@dataclass
class WeekEvaluation:
    week: int
    auc: float
    median_field_percentile: float  # where a real top lineup scores within the field (higher = better; 100 = best)
    share_in_field_top10: float
    share_in_field_top1: float


def evaluate(d: WeekData, weights: np.ndarray) -> WeekEvaluation:
    real_score = d.real_z @ weights
    field_score = d.field_z @ weights
    order = np.argsort(field_score)
    sorted_scores = field_score[order]
    cumulative = np.cumsum(d.field_weights[order])
    # Fraction of the field scoring BELOW each real lineup.
    pos = np.searchsorted(sorted_scores, real_score, side="left")
    below = np.where(pos > 0, cumulative[np.minimum(pos, len(cumulative)) - 1], 0.0)
    below = np.where(pos >= len(cumulative), 1.0, below)
    # AUC = P(real score > a random field score) (ties count half; negligible).
    auc = float(below.mean())
    return WeekEvaluation(
        week=d.week,
        auc=auc,
        median_field_percentile=float(np.median(below) * 100),
        share_in_field_top10=float((below >= 0.90).mean()),
        share_in_field_top1=float((below >= 0.99).mean()),
    )


def describe_weights(weights: np.ndarray) -> list[tuple[str, float]]:
    return sorted(zip(FEATURE_NAMES, weights.tolist()), key=lambda kv: -abs(kv[1]))
