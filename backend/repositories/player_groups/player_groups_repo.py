"""Persists the week's player groups as JSON, one file per (season, week,
platform, contest): "{prefix}_player_groups_{contest_slug}_week{week}.json"
under data/nfl/{season}/ -- same layout as the other per-week files."""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.player_groups.player_groups import PlayerGroup
from backend.services.platform_settings.prefix import contest_slug, platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    return nfl_data_dir / str(season) / f"{platform_file_prefix(platform)}_player_groups_{contest_slug(contest)}_week{week}.json"


def save_groups(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, groups: list[PlayerGroup]) -> None:
    path = _path(nfl_data_dir, season, week, platform, contest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"groups": [g.model_dump() for g in groups]}, indent=2), encoding="utf-8")


def load_groups(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> list[PlayerGroup]:
    path = _path(nfl_data_dir, season, week, platform, contest)
    if not path.exists():
        return []
    return [PlayerGroup(**g) for g in json.loads(path.read_text(encoding="utf-8"))["groups"]]
