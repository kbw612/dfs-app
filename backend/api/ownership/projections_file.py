"""
GET /projections-file?season=&week=&platform= (mounted at
/api/ownership/projections-file -- see backend/api/ownership/__init__.py).
Returns the raw CSV uploaded via POST /upload-projections-csv for that
(season, week, platform), as text/csv -- lets the Settings tab link
straight to the file for viewing/downloading rather than re-displaying
its contents in-app. `platform` defaults to "DraftKings". 404 if
nothing's been uploaded yet.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.config import settings
from backend.repositories.ownership.projections_repo import load_projections_csv

router = APIRouter()


@router.get("/projections-file", response_class=PlainTextResponse)
def ownership_projections_file_endpoint(season: int, week: int, platform: str = "DraftKings") -> PlainTextResponse:
    try:
        csv_text = load_projections_csv(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ownership projections file uploaded yet for season {season} week {week}.",
        )
    return PlainTextResponse(content=csv_text, media_type="text/csv")
