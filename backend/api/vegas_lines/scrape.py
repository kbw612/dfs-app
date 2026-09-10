"""
POST /scrape?season=&week= (mounted at /api/vegas-lines/scrape -- see
backend/api/vegas_lines/__init__.py). Scrapes oneweekseason.com's public
week page (backend/services/vegas_lines/scraper.py) and merges the result
into whatever was already saved for that (season, week) -- see
services/vegas_lines/merge.py's docstring for the "initial never changes,
current always does" rule. This never touches Game Environment/scoring by
itself; see backend/api/vegas_lines/apply.py for that explicit, separate
step.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.vegas_lines.vegas_lines_repo import load_vegas_lines, save_vegas_lines
from backend.schemas.vegas_lines.vegas_lines import VegasLinesSnapshot
from backend.services.vegas_lines.merge import merge_vegas_lines
from backend.services.vegas_lines.scraper import scrape as run_scrape

router = APIRouter()


class VegasLinesScrapeResult(BaseModel):
    snapshot: VegasLinesSnapshot
    messages: list[str]


@router.post("/scrape", response_model=VegasLinesScrapeResult)
def vegas_lines_scrape_endpoint(season: int, week: int) -> VegasLinesScrapeResult:
    scraped_games, messages = run_scrape(season, week)
    existing = load_vegas_lines(settings.nfl_data_dir, season, week)
    scraped_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    snapshot = merge_vegas_lines(existing, scraped_games, season, week, scraped_at)
    save_vegas_lines(settings.nfl_data_dir, snapshot)
    return VegasLinesScrapeResult(snapshot=snapshot, messages=messages)
