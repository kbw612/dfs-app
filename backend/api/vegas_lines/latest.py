"""
GET /latest?season=&week= (mounted at /api/vegas-lines/latest -- see
backend/api/vegas_lines/__init__.py). 404s if nothing's been scraped yet
for that (season, week) -- same "no file yet" convention as every other
per-week "latest" endpoint in this app (e.g. backend/api/player_pool/
latest.py's DK-salary-not-uploaded case), so the frontend can show a
"retrieve it first" hint rather than an empty/broken table.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.vegas_lines.vegas_lines_repo import load_vegas_lines
from backend.schemas.vegas_lines.vegas_lines import VegasLinesSnapshot

router = APIRouter()


@router.get("/latest", response_model=VegasLinesSnapshot)
def vegas_lines_latest_endpoint(season: int, week: int) -> VegasLinesSnapshot:
    snapshot = load_vegas_lines(settings.nfl_data_dir, season, week)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No Vegas Lines scraped yet for season {season} week {week} -- retrieve them first.",
        )
    return snapshot
