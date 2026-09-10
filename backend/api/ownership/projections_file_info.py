"""
GET /projections-file-info?season=&week=&platform= (mounted at
/api/ownership/projections-file-info -- see
backend/api/ownership/__init__.py). The filename and upload timestamp
(the current file's on-disk modified time) for whatever's currently saved
for that (season, week, platform), plus initial_uploaded_at -- the
*initial* file's own modified time (see
backend/repositories/ownership/projections_repo.py's docstring), equal to
uploaded_at when this (season, week, platform) has only ever been
uploaded once. Lets Settings show both "Initial uploaded <timestamp>" and
"Last uploaded <timestamp>" without fetching/displaying either file's
actual content (see GET /projections-file for that). `platform` defaults
to "DraftKings". 404 if nothing's been uploaded yet.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.projections_repo import initial_projections_csv_path, projections_csv_path

router = APIRouter()


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


class OwnershipProjectionsFileInfo(BaseModel):
    filename: str
    uploaded_at: str
    initial_uploaded_at: str


@router.get("/projections-file-info", response_model=OwnershipProjectionsFileInfo)
def ownership_projections_file_info_endpoint(
    season: int, week: int, platform: str = "DraftKings"
) -> OwnershipProjectionsFileInfo:
    try:
        file_path = projections_csv_path(settings.nfl_data_dir, season, week, platform)
        initial_path = initial_projections_csv_path(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No ownership projections file uploaded yet for season {season} week {week}.",
        )
    uploaded_at = _mtime_iso(file_path)
    initial_uploaded_at = _mtime_iso(initial_path) if initial_path.exists() else uploaded_at
    return OwnershipProjectionsFileInfo(
        filename=file_path.name, uploaded_at=uploaded_at, initial_uploaded_at=initial_uploaded_at
    )
