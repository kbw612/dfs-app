"""
Persists VegasLinesSnapshot (backend/schemas/vegas_lines/vegas_lines.py)
-- one file per (season, week), same one-file-per-week layout as
repositories/player_pool/entries_repo.py, under the shared per-season
nfl_data_dir root (see backend/config.py's nfl_data_dir).

Shape on disk (data/nfl/{season}/vegas_lines_week{week}.json): the
VegasLinesSnapshot's own fields, verbatim (season/week are still included
here despite being implied by the path, same redundancy every other
per-week resource in this app accepts for a self-describing file).

save_vegas_lines() always fully replaces whatever was saved for that
(season, week) -- the caller (backend/api/vegas_lines/scrape.py, via
services/vegas_lines/merge.py) is responsible for carrying `initial`
forward itself; this repo has no merge logic of its own.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.vegas_lines.vegas_lines import VegasLinesSnapshot


def _path(nfl_data_dir: Path, season: int, week: int) -> Path:
    return nfl_data_dir / str(season) / f"vegas_lines_week{week}.json"


def save_vegas_lines(nfl_data_dir: Path, snapshot: VegasLinesSnapshot) -> None:
    path = _path(nfl_data_dir, snapshot.season, snapshot.week)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.model_dump(), indent=2), encoding="utf-8")


def load_vegas_lines(nfl_data_dir: Path, season: int, week: int) -> VegasLinesSnapshot | None:
    path = _path(nfl_data_dir, season, week)
    if not path.exists():
        return None
    return VegasLinesSnapshot(**json.loads(path.read_text(encoding="utf-8")))
