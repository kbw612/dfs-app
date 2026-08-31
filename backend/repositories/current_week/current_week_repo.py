"""
Persists the single current-week pointer (backend/schemas/current_week/
current_week.py) -- one small JSON file, not one per season/week, since
there's only ever one "current" value at a time.

Shape on disk (data/current_week/current_week.json):

    {"season": 2026, "week": 3}
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.current_week.current_week import CurrentWeek

_FILENAME = "current_week.json"


def _path(current_week_dir: Path) -> Path:
    return current_week_dir / _FILENAME


def load_current_week(current_week_dir: Path) -> CurrentWeek | None:
    """None if nothing's ever been saved yet -- the caller decides what
    default to hand back to a first-time caller (see the API layer)."""
    path = _path(current_week_dir)
    if not path.exists():
        return None
    return CurrentWeek(**json.loads(path.read_text(encoding="utf-8")))


def save_current_week(current_week_dir: Path, entry: CurrentWeek) -> None:
    current_week_dir.mkdir(parents=True, exist_ok=True)
    _path(current_week_dir).write_text(entry.model_dump_json(indent=2), encoding="utf-8")
