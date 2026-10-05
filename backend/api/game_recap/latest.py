"""
GET /latest?season=&week= (mounted at /api/game-recap/latest -- see
backend/api/game_recap/__init__.py). 404s if nothing's been scraped yet
for that (season, week) -- same "no file yet" convention as every other
per-week "latest" endpoint in this app (e.g. backend/api/vegas_lines/
latest.py), so the frontend can show a "not scraped yet" hint rather than
an empty/broken table.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.game_recap.game_recap_repo import load_game_recaps
from backend.schemas.game_recap.game_recap import GameRecapWeekSnapshot

router = APIRouter()


@router.get("/latest", response_model=GameRecapWeekSnapshot)
def game_recap_latest_endpoint(season: int, week: int) -> GameRecapWeekSnapshot:
    snapshot = load_game_recaps(settings.nfl_data_dir, season, week)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No game recaps scraped yet for season {season} week {week} -- scrape them first.",
        )
    return snapshot
