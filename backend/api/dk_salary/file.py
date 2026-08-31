"""
GET /file?season=&week=&platform= (mounted at /api/dk-salary/file -- see
backend/api/dk_salary/__init__.py). Returns the raw CSV uploaded via POST
/import-csv for that (season, week, platform), as text/csv -- lets the
Settings tab link straight to the file for viewing/downloading. `platform`
defaults to "DraftKings", same as /import-csv. 404 if nothing's been
uploaded yet.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv

router = APIRouter()


@router.get("/file", response_class=PlainTextResponse)
def dk_salary_file_endpoint(season: int, week: int, platform: str = "DraftKings") -> PlainTextResponse:
    try:
        csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=f"No DK salary file uploaded yet for season {season} week {week}.",
        )
    return PlainTextResponse(content=csv_text, media_type="text/csv")
