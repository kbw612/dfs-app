"""
Persists Salary Multiplier's explicit per-platform overrides (see
backend/schemas/salary_multiplier/salary_multiplier.py) -- a single JSON
file shared across every platform, not one-per-season/week like most of
this app's other data, since a multiplier isn't scoped to either.

Only *overrides* are stored here -- a platform that's never had its
multiplier touched has no entry in this file at all, and
backend/services/salary_multiplier/engine.py's default_multiplier()
decides its resolved value instead (4.0 for DraftKings today). Saving
`None` clears the override entirely (removes the key) rather than
storing a null, so the file only ever holds real numbers.

Shape on disk (data/salary_multiplier/by_platform.json):

    {"DraftKings": 4.5}
"""

from __future__ import annotations

import json
from pathlib import Path

_FILENAME = "by_platform.json"


def _path(salary_multiplier_dir: Path) -> Path:
    return salary_multiplier_dir / _FILENAME


def load_multipliers(salary_multiplier_dir: Path) -> dict[str, float]:
    """Empty dict if nothing's ever been overridden yet for any
    platform -- every platform falls back to its computed default (see
    engine.py)."""
    path = _path(salary_multiplier_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_multiplier(salary_multiplier_dir: Path, platform: str, multiplier: float | None) -> None:
    path = _path(salary_multiplier_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    multipliers = load_multipliers(salary_multiplier_dir)
    if multiplier is None:
        multipliers.pop(platform, None)
    else:
        multipliers[platform] = multiplier
    path.write_text(json.dumps(multipliers, indent=2), encoding="utf-8")
