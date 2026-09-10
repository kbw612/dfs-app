"""
POST /weekly-stats/import-csv?season=&week=&position= and
GET /weekly-stats/file-info?season=&week= (mounted at
/api/dk-players/weekly-stats/...). The 4 per-position FantasyData stat
uploads (QB/RB/WR/TE) that feed calculate-week-points -- see
backend/repositories/dk_players/weekly_stats_repo.py. Import just saves
the raw CSV text (parsed fresh on every read, same "always overwritten"
convention as every other upload here); file-info reports all 4
positions' status at once so Settings can show a single combined panel.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_players.weekly_stats_repo import (
    Position,
    save_weekly_stats_csv,
    weekly_stats_csv_path,
)
from backend.schemas.dk_players.dk_players import WeeklyStatsImportResult

router = APIRouter()

_POSITIONS: list[Position] = ["QB", "RB", "WR", "TE"]


@router.post("/weekly-stats/import-csv", response_model=WeeklyStatsImportResult)
async def import_weekly_stats_csv_endpoint(
    season: int, week: int, position: Literal["QB", "RB", "WR", "TE"], file: UploadFile = File(...)
) -> WeeklyStatsImportResult:
    raw_bytes = await file.read()
    csv_text = raw_bytes.decode("utf-8-sig")
    save_weekly_stats_csv(settings.nfl_data_dir, season, week, position, csv_text)
    row_count = max(csv_text.strip().count("\n"), 0)  # header line doesn't count as a row
    return WeeklyStatsImportResult(season=season, week=week, position=position, row_count=row_count)


class WeeklyStatsFileStatus(BaseModel):
    position: str
    filename: str | None
    uploaded_at: str | None


class WeeklyStatsFileInfoResult(BaseModel):
    files: list[WeeklyStatsFileStatus]


@router.get("/weekly-stats/file-info", response_model=WeeklyStatsFileInfoResult)
def weekly_stats_file_info_endpoint(season: int, week: int) -> WeeklyStatsFileInfoResult:
    statuses = []
    for position in _POSITIONS:
        file_path = weekly_stats_csv_path(settings.nfl_data_dir, season, week, position)
        if file_path.exists():
            uploaded_at = datetime.fromtimestamp(file_path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
            statuses.append(WeeklyStatsFileStatus(position=position, filename=file_path.name, uploaded_at=uploaded_at))
        else:
            statuses.append(WeeklyStatsFileStatus(position=position, filename=None, uploaded_at=None))
    return WeeklyStatsFileInfoResult(files=statuses)
