"""
Persists the single platform/contest pointer (backend/schemas/
platform_settings/platform_settings.py) -- one small JSON file, not one
per season/week, since there's only ever one "current" value at a time
(same shape as backend/repositories/current_week/current_week_repo.py).

Shape on disk (data/platform_settings/platform_settings.json):

    {"platform": "DraftKings", "contest": "Classic Main"}
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.platform_settings.platform_settings import PlatformSettings

_FILENAME = "platform_settings.json"


def _path(platform_settings_dir: Path) -> Path:
    return platform_settings_dir / _FILENAME


def load_platform_settings(platform_settings_dir: Path) -> PlatformSettings | None:
    """None if nothing's ever been saved yet -- the caller decides what
    default to hand back to a first-time caller (see the API layer)."""
    path = _path(platform_settings_dir)
    if not path.exists():
        return None
    return PlatformSettings(**json.loads(path.read_text(encoding="utf-8")))


def save_platform_settings(platform_settings_dir: Path, entry: PlatformSettings) -> None:
    platform_settings_dir.mkdir(parents=True, exist_ok=True)
    _path(platform_settings_dir).write_text(entry.model_dump_json(indent=2), encoding="utf-8")
