"""
Persists explicit per-player selection overrides for Player Selection (see
backend/schemas/player_selection/player_selection.py) -- one small JSON
file per (season, week, platform), living under the same data/nfl/
{season}/ layout as the salary/ownership files themselves (see
backend/config.py's nfl_data_dir and backend/services/platform_settings/
prefix.py for the filename prefix).

Only *overrides* are stored here -- a player who's never had their
checkbox touched has no entry in this file at all, and
backend/services/player_selection/engine.py's default_selected() decides
their selected state from position + salary instead. This keeps the file
small and means a newly-uploaded salary file (different players, possibly
different salaries) doesn't need any migration -- names that no longer
appear in this week's file just sit unused in the override map.

Shape on disk (data/nfl/{season}/{prefix}_player_selection_week{week}.json):

    {"Josh Allen": true, "Some Backup RB": false}
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.platform_settings.prefix import platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str) -> Path:
    prefix = platform_file_prefix(platform)
    return nfl_data_dir / str(season) / f"{prefix}_player_selection_week{week}.json"


def load_overrides(nfl_data_dir: Path, season: int, week: int, platform: str) -> dict[str, bool]:
    """Empty dict if nothing's ever been overridden yet for this (season,
    week, platform) -- every player just falls back to their computed
    default (see engine.py)."""
    path = _path(nfl_data_dir, season, week, platform)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_override(nfl_data_dir: Path, season: int, week: int, platform: str, player: str, selected: bool) -> None:
    path = _path(nfl_data_dir, season, week, platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    overrides = load_overrides(nfl_data_dir, season, week, platform)
    overrides[player] = selected
    path.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
