"""
GET /file-info?season=&week=&platform= (mounted at
/api/contest-results/file-info -- see backend/api/contest_results/
__init__.py). Just the filename and upload timestamp (the file's on-disk
modified time) for whatever contest standings export is currently saved
for that (season, week, platform) -- same shape/purpose as DK Salary's
own /api/dk-salary/file-info, lets Settings show "<filename> modified
<timestamp>" without fetching the file's actual content. `platform`
defaults to "DraftKings". 404 if nothing's been uploaded yet.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import contest_standings_csv_path

router = APIRouter()


class ContestStandingsFileInfo(BaseModel):
    filename: str
    uploaded_at: str


@router.get("/file-info", response_model=ContestStandingsFileInfo)
def contest_standings_file_info_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"
) -> ContestStandingsFileInfo:
    file_path = contest_standings_csv_path(settings.nfl_data_dir, season, week, platform, contest)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No contest standings uploaded yet for season {season} week {week}.",
        )
    uploaded_at = datetime.fromtimestamp(file_path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    return ContestStandingsFileInfo(filename=file_path.name, uploaded_at=uploaded_at)
