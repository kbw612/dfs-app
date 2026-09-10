"""
Persists the single platform/contest pointer (backend/schemas/
platform_settings/platform_settings.py) -- one small JSON file per season,
not per week, since there's only ever one "current" value at a time within
a season. Lives under the shared per-season nfl_data_dir layout (same root
as dk_salary/player_selection/player_defaults -- see backend/config.py's
nfl_data_dir).

Shape on disk (data/nfl/{season}/settings/platform_settings.json):

    {"platform": "DraftKings", "contest": "Classic Main"}
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.platform_settings.platform_settings import PlatformSettings

_FILENAME = "platform_settings.json"


def _path(nfl_data_dir: Path, season: int) -> Path:
    return nfl_data_dir / str(season) / "settings" / _FILENAME


def load_platform_settings(nfl_data_dir: Path, season: int) -> PlatformSettings | None:
    """None if nothing's ever been saved yet for this season -- the caller
    decides what default to hand back to a first-time caller (see the API
    layer)."""
    path = _path(nfl_data_dir, season)
    if not path.exists():
        return None
    fields = json.loads(path.read_text(encoding="utf-8"))
    return PlatformSettings(season=season, **fields)


def save_platform_settings(nfl_data_dir: Path, entry: PlatformSettings) -> None:
    path = _path(nfl_data_dir, entry.season)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(entry.model_dump(exclude={"season"}), indent=2),
        encoding="utf-8",
    )
