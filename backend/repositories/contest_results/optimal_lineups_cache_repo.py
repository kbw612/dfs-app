"""
Persists the generated Optimal Lineups pool (see backend/services/
contest_results/lineup_generators.py's build_top10_by_points) to disk as
JSON, so the expensive generation (an exact k-best search) only has to
run once per (season, week, platform, contest) -- the frontend's own
"Optimal Lineups" panel generates on first visit and reads this cached
file on every later visit instead of recomputing (see backend/api/
contest_results/optimal_lineup_pools.py).

Same "{prefix}_{descriptor}_{contest_slug}_week{week}" naming convention
as every other contest-scoped file in this app (see
contest_standings_repo.py's own docstring for that convention), just
with a .json extension since the content here is a small structured
object (a list of OptimalLineup), not a big flat CSV table:
  "dk_contest_optimal_lineups_classic_main_week1.json"

Same "always overwritten, no history of old generations kept" convention
as the salary/contest-standings files too -- calling save_* again (e.g.
after a "regenerate" action) always replaces whatever was cached before,
there's only ever one "current" pool per (season, week, platform,
contest).
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.contest_results.contest_results import OptimalLineup
from backend.services.platform_settings.prefix import contest_slug, platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, descriptor: str) -> Path:
    prefix = platform_file_prefix(platform)
    slug = contest_slug(contest)
    return nfl_data_dir / str(season) / f"{prefix}_{descriptor}_{slug}_week{week}.json"


def top10_by_points_path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    return _path(nfl_data_dir, season, week, platform, contest, "contest_optimal_lineups")


def _save(path: Path, lineups: list[OptimalLineup]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"lineups": [lineup.model_dump() for lineup in lineups]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _load(path: Path) -> list[OptimalLineup] | None:
    """None if nothing's been generated (and cached) yet at this path --
    same "missing file means not-yet-done, not an error" convention as
    contest_standings_repo.load_contest_standings_csv."""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return [OptimalLineup.model_validate(item) for item in data.get("lineups", [])]


def save_top10_by_points(
    nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, lineups: list[OptimalLineup]
) -> Path:
    return _save(top10_by_points_path(nfl_data_dir, season, week, platform, contest), lineups)


def load_top10_by_points(
    nfl_data_dir: Path, season: int, week: int, platform: str, contest: str
) -> list[OptimalLineup] | None:
    return _load(top10_by_points_path(nfl_data_dir, season, week, platform, contest))
