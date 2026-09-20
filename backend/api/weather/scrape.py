"""
POST /scrape?season=&week= (mounted at /api/weather/scrape -- see
backend/api/weather/__init__.py). Scrapes mysportsweather.com/nfl's
current "Kevin's note" cards (backend/services/weather/scraper.py) and
saves the result as this (season, week)'s WeatherSnapshot, fully replacing
whatever was there before -- no merge step, unlike Vegas Lines (see
backend/repositories/weather/weather_repo.py's docstring for why).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.weather.weather_repo import save_weather
from backend.schemas.weather.weather import WeatherGame, WeatherSnapshot
from backend.services.weather.scraper import scrape as run_scrape

router = APIRouter()


class WeatherScrapeResult(BaseModel):
    snapshot: WeatherSnapshot
    messages: list[str]


@router.post("/scrape", response_model=WeatherScrapeResult)
def weather_scrape_endpoint(season: int, week: int) -> WeatherScrapeResult:
    scraped_notes, messages = run_scrape()
    scraped_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    snapshot = WeatherSnapshot(
        season=season,
        week=week,
        scraped_at=scraped_at,
        games=[
            WeatherGame(
                away_name=note.away_name,
                home_name=note.home_name,
                away_team=note.away_team,
                home_team=note.home_team,
                game_key=note.game_key,
                kickoff_label=note.kickoff_label,
                color=note.color,
                note=note.note,
            )
            for note in scraped_notes
        ],
    )
    save_weather(settings.nfl_data_dir, snapshot)
    return WeatherScrapeResult(snapshot=snapshot, messages=messages)
