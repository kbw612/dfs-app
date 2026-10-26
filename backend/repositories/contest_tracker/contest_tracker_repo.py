"""Persists the Results Tracker as one JSON file per season:
data/nfl/{season}/contest_tracker.json. Written atomically (temp file, then
rename) so an interrupted save can't corrupt the person's history."""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend.schemas.contest_tracker.contest_tracker import TrackerFile


def _path(nfl_data_dir: Path, season: int) -> Path:
    return nfl_data_dir / str(season) / "contest_tracker.json"


def load_tracker(nfl_data_dir: Path, season: int) -> TrackerFile:
    path = _path(nfl_data_dir, season)
    if not path.exists():
        return TrackerFile(season=season)
    return TrackerFile(**json.loads(path.read_text(encoding="utf-8")))


def save_tracker(nfl_data_dir: Path, data: TrackerFile) -> None:
    path = _path(nfl_data_dir, data.season)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data.model_dump(), indent=2), encoding="utf-8")
    os.replace(tmp, path)
