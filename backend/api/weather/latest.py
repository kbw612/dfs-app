"""
GET /latest?season=&week= (mounted at /api/weather/latest -- see
backend/api/weather/__init__.py). 404s if nothing's been scraped yet for
that (season, week) -- same "no file yet" convention as every other
per-week "latest" endpoint in this app (e.g. backend/api/vegas_lines/
latest.py), so the frontend can show a "retrieve it first" hint rather
than an empty/broken list.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.weather.weather_repo import load_weather
from backend.schemas.weather.weather import WeatherSnapshot

router = APIRouter()


@router.get("/latest", response_model=WeatherSnapshot)
def weather_latest_endpoint(season: int, week: int) -> WeatherSnapshot:
    snapshot = load_weather(settings.nfl_data_dir, season, week)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No Weather scraped yet for season {season} week {week} -- retrieve it first.",
        )
    return snapshot
