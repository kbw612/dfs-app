"""
GET /file-info?season=&week=&platform= (mounted at
/api/dk-salary/file-info -- see backend/api/dk_salary/__init__.py). Just
the filename and upload timestamp (the file's on-disk modified time) for
whatever's currently saved for that (season, week, platform) -- lets
Settings show "<filename> modified <timestamp>" without fetching/
displaying the file's actual content (see GET /file for that). `platform`
defaults to "DraftKings". 404 if nothing's been uploaded yet.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import salary_csv_path

router = APIRouter()


class DkSalaryFileInfo(BaseModel):
    filename: str
    uploaded_at: str


@router.get("/file-info", response_model=DkSalaryFileInfo)
def dk_salary_file_info_endpoint(season: int, week: int, platform: str = "DraftKings") -> DkSalaryFileInfo:
    try:
        file_path = salary_csv_path(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No DK salary file uploaded yet for season {season} week {week}.",
        )
    uploaded_at = datetime.fromtimestamp(file_path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    return DkSalaryFileInfo(filename=file_path.name, uploaded_at=uploaded_at)
