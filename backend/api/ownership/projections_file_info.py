"""
GET /projections-file-info?season=&week=&platform= (mounted at
/api/ownership/projections-file-info -- see
backend/api/ownership/__init__.py). Just the filename and upload
timestamp (the file's on-disk modified time) for whatever's currently
saved for that (season, week, platform) -- lets Settings show "<filename>
modified <timestamp>" without fetching/displaying the file's actual
content (see GET /projections-file for that). `platform` defaults to
"DraftKings". 404 if nothing's been uploaded yet.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.projections_repo import projections_csv_path

router = APIRouter()


class OwnershipProjectionsFileInfo(BaseModel):
    filename: str
    uploaded_at: str


@router.get("/projections-file-info", response_model=OwnershipProjectionsFileInfo)
def ownership_projections_file_info_endpoint(
    season: int, week: int, platform: str = "DraftKings"
) -> OwnershipProjectionsFileInfo:
    try:
        file_path = projections_csv_path(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No ownership projections file uploaded yet for season {season} week {week}.",
        )
    uploaded_at = datetime.fromtimestamp(file_path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    return OwnershipProjectionsFileInfo(filename=file_path.name, uploaded_at=uploaded_at)
