"""
Persists a person's own uploaded batch of externally-optimizer-generated
lineups, unparsed -- one file per (season, week, platform, contest),
always overwritten on the next upload, same "always overwritten,
re-parsed fresh on every read" convention as backend/repositories/
dk_salary/salary_snapshot_repo.py (see that module's docstring for why:
there's only ever one "current" lineup batch for a given week/contest,
no history of re-uploads kept).

Filename is "{prefix}_lineups_{contest_slug}_week{week}.csv", same shape
as the salary file's own "_salaries_{contest_slug}_" naming, where
prefix/contest_slug come from backend/services/platform_settings/
prefix.py's platform_file_prefix()/contest_slug(). Every contest gets its
own fully independent file this way, same as every other contest-scoped
upload in this app.
"""

from __future__ import annotations

from pathlib import Path

from backend.services.platform_settings.prefix import contest_slug, platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    prefix = platform_file_prefix(platform)
    slug = contest_slug(contest)
    return nfl_data_dir / str(season) / f"{prefix}_lineups_{slug}_week{week}.csv"


def lineup_upload_csv_path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    """The deterministic path for this (season, week, platform, contest)'s
    file, whether or not it exists yet -- same convention as
    salary_csv_path/contest_standings_csv_path."""
    return _path(nfl_data_dir, season, week, platform, contest)


def save_lineup_upload_csv(
    nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, csv_text: str
) -> Path:
    file_path = _path(nfl_data_dir, season, week, platform, contest)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(csv_text, encoding="utf-8")
    return file_path


def load_lineup_upload_csv(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> str | None:
    """None if nothing's been uploaded yet for this (season, week,
    platform, contest)."""
    file_path = _path(nfl_data_dir, season, week, platform, contest)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")
