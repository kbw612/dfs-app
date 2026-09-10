"""
Persists the 4 weekly FantasyData stat exports (QB/RB/WR/TE -- see
backend/services/dk_players/weekly_stats_loader.py for the column shape
each one has) that feed DK Players' calculate_week_points(). One file per
(season, week, position) -- these are league-wide stats, not tied to a DK
platform/contest, so there's no platform dimension here at all (unlike
every other per-week file in this app). Same "always overwritten,
re-parsed fresh on every read" convention as salary_snapshot_repo.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

Position = Literal["QB", "RB", "WR", "TE"]


def _path(nfl_data_dir: Path, season: int, week: int, position: Position) -> Path:
    return nfl_data_dir / str(season) / f"weekly_stats_{position.lower()}_week{week}.csv"


def weekly_stats_csv_path(nfl_data_dir: Path, season: int, week: int, position: Position) -> Path:
    return _path(nfl_data_dir, season, week, position)


def save_weekly_stats_csv(nfl_data_dir: Path, season: int, week: int, position: Position, csv_text: str) -> Path:
    file_path = _path(nfl_data_dir, season, week, position)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(csv_text, encoding="utf-8")
    return file_path


def load_weekly_stats_csv(nfl_data_dir: Path, season: int, week: int, position: Position) -> str | None:
    file_path = _path(nfl_data_dir, season, week, position)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")
