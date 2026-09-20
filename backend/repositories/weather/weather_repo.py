"""
Persists WeatherSnapshot (backend/schemas/weather/weather.py) -- one file
per (season, week), same one-file-per-week layout as
repositories/vegas_lines/vegas_lines_repo.py, under the shared per-season
nfl_data_dir root (see backend/config.py's nfl_data_dir).

Shape on disk (data/nfl/{season}/weather_week{week}.json): the
WeatherSnapshot's own fields, verbatim.

save_weather() always fully replaces whatever was saved for that
(season, week) -- there's no merge concept here (unlike Vegas Lines'
initial-vs-current split), since the source page only ever shows the
current week's forecast; a re-scrape is just a fresh snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.weather.weather import WeatherSnapshot


def _path(nfl_data_dir: Path, season: int, week: int) -> Path:
    return nfl_data_dir / str(season) / f"weather_week{week}.json"


def save_weather(nfl_data_dir: Path, snapshot: WeatherSnapshot) -> None:
    path = _path(nfl_data_dir, snapshot.season, snapshot.week)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.model_dump(), indent=2), encoding="utf-8")


def load_weather(nfl_data_dir: Path, season: int, week: int) -> WeatherSnapshot | None:
    path = _path(nfl_data_dir, season, week)
    if not path.exists():
        return None
    return WeatherSnapshot(**json.loads(path.read_text(encoding="utf-8")))
