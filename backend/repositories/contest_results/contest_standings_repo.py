"""
Persists this week's raw DK contest standings export, unparsed -- same
"one file per (season, week, platform, contest), always overwritten,
re-parsed fresh on every read" convention as backend/repositories/
dk_salary/salary_snapshot_repo.py (see that module's docstring for why:
there's only ever one "current" file for a given week/contest, no history
of re-uploads kept).

Filename is "{prefix}_contest_standings_{contest_slug}_week{week}.csv"
(underscores throughout, matching every other file in this app's naming
convention -- e.g. the salary file's own "_salaries_{contest_slug}_"
shape), where prefix/contest_slug come from backend/services/
platform_settings/prefix.py's platform_file_prefix()/contest_slug().
Every contest gets its own fully independent file this way (e.g.
"dk_contest_standings_classic_main_week3.csv" vs.
"dk_contest_standings_all_games_week3.csv").
"""

from __future__ import annotations

from pathlib import Path

from backend.services.platform_settings.prefix import contest_slug, platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    prefix = platform_file_prefix(platform)
    slug = contest_slug(contest)
    return nfl_data_dir / str(season) / f"{prefix}_contest_standings_{slug}_week{week}.csv"


def contest_standings_csv_path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    """The deterministic path for this (season, week, platform, contest)'s
    file, whether or not it exists yet -- used by the file-info endpoint
    to check existence/mtime directly rather than reading the whole file
    just to confirm it's there (see load_contest_standings_csv)."""
    return _path(nfl_data_dir, season, week, platform, contest)


def save_contest_standings_csv(
    nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, csv_text: str
) -> Path:
    file_path = _path(nfl_data_dir, season, week, platform, contest)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(csv_text, encoding="utf-8")
    return file_path


def load_contest_standings_csv(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> str | None:
    """None if nothing's been uploaded yet for this (season, week,
    platform, contest)."""
    file_path = _path(nfl_data_dir, season, week, platform, contest)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")
