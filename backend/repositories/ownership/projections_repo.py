"""
Persists this week's raw ownership projections CSV as uploaded via the
Settings tab -- one file per (season, week), always overwritten on the
next upload, same "just the raw file, re-parsed on read" pattern as
backend/repositories/dk_salary/salary_snapshot_repo.py. Lives under the
same new data/nfl/{season}/ layout (see backend/config.py's nfl_data_dir).

Distinct from ownership_snapshots_dir/snapshot_repo.py, which backs the
Ownership tab's own scrape/mock-CSV-driven analysis (leverage, pivots,
etc., via OwnershipSnapshot) -- that flow is untouched for now. This
upload exists so a projections file can be captured and viewed each week
without waiting on that flow's own scrape work; wiring it into the
Ownership tab's analysis is a separate future step.
"""

from __future__ import annotations

from pathlib import Path

from backend.services.platform_settings.prefix import platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str) -> Path:
    prefix = platform_file_prefix(platform)
    return nfl_data_dir / str(season) / f"{prefix}_ownership_projections_week{week}.csv"


def projections_csv_path(nfl_data_dir: Path, season: int, week: int, platform: str) -> Path:
    """The deterministic path for this (season, week, platform)'s file,
    whether or not it exists yet -- used by the file-info endpoint to
    check existence/mtime directly rather than reading the whole file
    just to confirm it's there (see load_projections_csv)."""
    return _path(nfl_data_dir, season, week, platform)


def save_projections_csv(nfl_data_dir: Path, season: int, week: int, platform: str, csv_text: str) -> Path:
    file_path = _path(nfl_data_dir, season, week, platform)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(csv_text, encoding="utf-8")
    return file_path


def load_projections_csv(nfl_data_dir: Path, season: int, week: int, platform: str) -> str | None:
    """None if nothing's been uploaded yet for this (season, week, platform)."""
    file_path = _path(nfl_data_dir, season, week, platform)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")
