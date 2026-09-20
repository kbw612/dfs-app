"""
Persists this week's raw DK salary CSV, unparsed -- one file per (season,
week, platform, contest), always overwritten on the next upload. There's
only ever one "current" salary file for a given week/contest (no history
of re-uploads kept, unlike ownership/depth-chart snapshots), so this is a
plain overwrite, not an append-only series of timestamped files.

Lives under the new data/nfl/{season}/ layout (see backend/config.py's
nfl_data_dir) rather than its own top-level directory -- Ownership and the
other snapshot-backed resources still use the old flat data/ layout for
now; they'll move under data/nfl/{season}/ too in a later pass.

Filename is "{prefix}_salaries_{contest_slug}_week{week}.csv" (plural
"salaries", matching DraftKings' own "all games" export naming), where
prefix comes from backend/services/platform_settings/prefix.py's
platform_file_prefix() (e.g. "dk" for "DraftKings") and contest_slug from
that same module's contest_slug() (e.g. "classic_main" for "Classic
Main") -- the season is already the parent directory, so it isn't
repeated in the filename. Every contest gets its own fully independent
file this way (e.g. "dk_salaries_classic_main_week3.csv" vs.
"dk_salaries_classic_all_games_week3.csv"), so switching the Contest chip in
Settings never overwrites another contest's upload. Deliberately stores
the raw CSV text as uploaded, not a parsed/JSON representation -- there's
nothing worth pre-computing here until a caller actually needs player
rows, at which point backend/services/dk_salary/dk_salary_loader.py's
parse_dk_salary_csv() reads this fresh (see backend/api/ownership/
position_blocks.py and backend/api/player_pool/latest.py).
"""

from __future__ import annotations

from pathlib import Path

from backend.services.platform_settings.prefix import contest_slug, platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    prefix = platform_file_prefix(platform)
    slug = contest_slug(contest)
    return nfl_data_dir / str(season) / f"{prefix}_salaries_{slug}_week{week}.csv"


def salary_csv_path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    """The deterministic path for this (season, week, platform, contest)'s
    file, whether or not it exists yet -- used by the file-info endpoint
    to check existence/mtime directly rather than reading the whole file
    just to confirm it's there (see load_salary_csv)."""
    return _path(nfl_data_dir, season, week, platform, contest)


def save_salary_csv(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, csv_text: str) -> Path:
    file_path = _path(nfl_data_dir, season, week, platform, contest)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(csv_text, encoding="utf-8")
    return file_path


def load_salary_csv(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> str | None:
    """None if nothing's been uploaded yet for this (season, week,
    platform, contest)."""
    file_path = _path(nfl_data_dir, season, week, platform, contest)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")
