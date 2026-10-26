"""
Persists the merged, de-duplicated optimizer pool for one (season, week,
platform, contest) as JSON: {"files": [{name, rows, new}], "lineups": [[[name,
id] x 9], ...]}. Filename "{prefix}_analyzer_pool_{contest_slug}_week{week}.json"
beside the other per-week uploads.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.platform_settings.prefix import contest_slug, platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    return nfl_data_dir / str(season) / f"{platform_file_prefix(platform)}_analyzer_pool_{contest_slug(contest)}_week{week}.json"


def save_pool(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, data: dict) -> None:
    path = _path(nfl_data_dir, season, week, platform, contest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def load_pool(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> dict | None:
    path = _path(nfl_data_dir, season, week, platform, contest)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _result_path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    return nfl_data_dir / str(season) / f"{platform_file_prefix(platform)}_analyzer_result_{contest_slug(contest)}_week{week}.json"


def save_result(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, data: dict) -> None:
    """The last analysis for this week -- {"saved_at", "request", "result"} --
    so switching weeks and back shows it without re-analyzing."""
    path = _result_path(nfl_data_dir, season, week, platform, contest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def load_result(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> dict | None:
    path = _result_path(nfl_data_dir, season, week, platform, contest)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def delete_result(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> None:
    _result_path(nfl_data_dir, season, week, platform, contest).unlink(missing_ok=True)
