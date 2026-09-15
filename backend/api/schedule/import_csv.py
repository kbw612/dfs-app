"""
POST /import-csv?season= (mounted at /api/schedule/import-csv -- see
backend/api/schedule/__init__.py). Saves the person's own full-season
Team/Week/Opponent/GameLocation schedule export as-is (raw CSV text,
re-parsed fresh on every read -- see schedule_repo.py's docstring), same
"always overwritten" convention as every other upload in this app. Not
scoped to week/platform/contest -- one file covers the whole season.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.schedule.schedule_repo import save_schedule_csv
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


class ScheduleImportResult(BaseModel):
    season: int
    row_count: int


@router.post("/import-csv", response_model=ScheduleImportResult)
async def import_schedule_csv_endpoint(season: int, file: UploadFile = File(...)) -> ScheduleImportResult:
    raw_bytes = await file.read()
    csv_text = raw_bytes.decode("utf-8-sig")
    rows = parse_schedule_csv(csv_text)
    save_schedule_csv(settings.nfl_data_dir, season, csv_text)
    return ScheduleImportResult(season=season, row_count=len(rows))
