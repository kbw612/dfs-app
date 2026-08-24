"""
Loads config/ownership-leverage-tiers.json -- the game-count -> leverage
point table used by compute_high_owned() (backend/services/ownership/
engine.py) to decide the ownership% threshold that counts as "chalk" for a
given slate size. Bigger slates dilute ownership across more players, so
the threshold drops as more games get added -- a small single-game slate
needs a much higher bar (50%) than a full 8+-game Sunday (20%).

A faithful, dumb parser like scoring_matrix_repo.py -- it doesn't decide
which tier applies to a given slate, just loads the ranges. `max_games:
null` in the JSON means "no upper bound" (the last, catch-all tier).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LeverageTier:
    min_games: int
    max_games: int | None  # None -- no upper bound (open-ended top tier)
    leverage_point: float


def load_leverage_tiers(json_path: Path) -> list[LeverageTier]:
    """Every configured tier, in file order. Empty list if the file
    doesn't exist yet (meaning: no tiers configured, so callers can't
    resolve a leverage point for any slate size)."""
    if not json_path.exists():
        return []

    data = json.loads(json_path.read_text(encoding="utf-8"))
    return [
        LeverageTier(
            min_games=entry["min_games"],
            max_games=entry.get("max_games"),
            leverage_point=entry["leverage_point"],
        )
        for entry in data.get("tiers", [])
    ]
