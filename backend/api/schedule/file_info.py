"""
GET /file-info?season= (mounted at /api/schedule/file-info). Just the
filename and upload timestamp for whatever schedule is currently saved
for this season -- same "<filename> modified <timestamp>" shape every
other file-info endpoint in this app returns (see e.g.
backend/api/dk_salary/file_info.py), minus the week/platform/contest
dimensions this file doesn't have. 404 if nothing's been uploaded yet.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.schedule.schedule_repo import schedule_csv_path

router = APIRouter()


class ScheduleFileInfo(BaseModel):
    filename: str
    uploaded_at: str


@router.get("/file-info", response_model=ScheduleFileInfo)
def schedule_file_info_endpoint(season: int) -> ScheduleFileInfo:
    file_path = schedule_csv_path(settings.nfl_data_dir, season)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"No schedule file uploaded yet for season {season}.")
    uploaded_at = datetime.fromtimestamp(file_path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    return ScheduleFileInfo(filename=file_path.name, uploaded_at=uploaded_at)
