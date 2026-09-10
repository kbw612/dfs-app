"""
Persists the DK Players season-long tracker (backend/schemas/dk_players/
dk_players.py) as one CSV per (season, platform) -- deliberately NOT the
"one file per (season, week, platform), always overwritten" convention
every other snapshot in this app follows (salary_snapshot_repo.py,
contest_standings_repo.py, ...). This file has no "current" version to
overwrite -- it's a running log that keeps growing (add_week_players) and
gets selectively backfilled (calculate_week_points) week over week, all
within backend/services/dk_players/dk_players_engine.py. The repo itself
stays a dumb raw-text load/save, same shape as every other repo here; the
engine is what parses, mutates, and re-serializes the CSV text in between.

Filename is "{prefix}_players.csv" (e.g. "dk_players.csv" for
"DraftKings") -- no week in the name, since one file covers the whole
season.
"""

from __future__ import annotations

from pathlib import Path

from backend.services.platform_settings.prefix import platform_file_prefix


def _path(nfl_data_dir: Path, season: int, platform: str) -> Path:
    prefix = platform_file_prefix(platform)
    return nfl_data_dir / str(season) / f"{prefix}_players.csv"


def dk_players_csv_path(nfl_data_dir: Path, season: int, platform: str) -> Path:
    return _path(nfl_data_dir, season, platform)


def save_dk_players_csv(nfl_data_dir: Path, season: int, platform: str, csv_text: str) -> Path:
    file_path = _path(nfl_data_dir, season, platform)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(csv_text, encoding="utf-8")
    return file_path


def load_dk_players_csv(nfl_data_dir: Path, season: int, platform: str) -> str | None:
    """None if this season/platform's tracker hasn't been started yet."""
    file_path = _path(nfl_data_dir, season, platform)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")
