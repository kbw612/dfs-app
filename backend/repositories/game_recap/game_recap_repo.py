"""
Persists GameRecapWeekSnapshot (backend/schemas/game_recap/game_recap.py)
-- one file per (season, week), same one-file-per-week layout as
repositories/vegas_lines/vegas_lines_repo.py, under the shared per-season
nfl_data_dir root (see backend/config.py's nfl_data_dir).

Shape on disk (data/nfl/{season}/game_recap_week{week}.json): the
GameRecapWeekSnapshot's own fields, verbatim (season/week are still
included here despite being implied by the path, same redundancy every
other per-week resource in this app accepts for a self-describing file).

save_game_recaps() always fully replaces whatever was saved for that
(season, week) -- unlike Vegas Lines there's no initial/current split to
preserve (see GameRecapWeekSnapshot's own docstring for why), so a
re-scrape is a plain overwrite.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.game_recap.game_recap import GameRecapWeekSnapshot


def _path(nfl_data_dir: Path, season: int, week: int) -> Path:
    return nfl_data_dir / str(season) / f"game_recap_week{week}.json"


def save_game_recaps(nfl_data_dir: Path, snapshot: GameRecapWeekSnapshot) -> None:
    path = _path(nfl_data_dir, snapshot.season, snapshot.week)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.model_dump(), indent=2), encoding="utf-8")


def load_game_recaps(nfl_data_dir: Path, season: int, week: int) -> GameRecapWeekSnapshot | None:
    path = _path(nfl_data_dir, season, week)
    if not path.exists():
        return None
    return GameRecapWeekSnapshot(**json.loads(path.read_text(encoding="utf-8")))
