"""
POST /upload-projections-csv?season=&week=&platform= (mounted at
/api/ownership/upload-projections-csv -- see
backend/api/ownership/__init__.py). Multipart upload of a single ownership
projections CSV (Player/Position/Team/Opponent/Salary/% ownership columns,
offense and DST rows together -- see backend/services/ownership/
csv_loader.py's parse_ownership_projections_csv). Parses it once here just
to report player_count/messages back to the caller, then saves the *raw*
CSV text as-is via projections_repo (one current file per (season, week,
platform), always overwritten -- same pattern as
backend/api/dk_salary/import_csv.py). `platform` (default "DraftKings")
picks the filename prefix -- see
backend/services/platform_settings/prefix.py.

This is the Settings tab's upload control -- separate from POST
/api/ownership/import-csv, which still drives the Ownership tab's own
scrape-stand-in/analysis flow (OwnershipSnapshot, leverage, pivots) and is
untouched by this. Wiring this upload into that analysis is future work.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.projections_repo import save_projections_csv
from backend.schemas.depth_charts.snapshot import Message
from backend.services.ownership.csv_loader import parse_ownership_projections_csv

router = APIRouter()


class OwnershipProjectionsImportResult(BaseModel):
    file_path: str
    season: int
    week: int
    player_count: int
    message_counts: dict[str, int]
    messages: list[Message]


@router.post("/upload-projections-csv", response_model=OwnershipProjectionsImportResult)
async def upload_ownership_projections_csv_endpoint(
    season: int, week: int, file: UploadFile = File(...), platform: str = "DraftKings"
) -> OwnershipProjectionsImportResult:
    raw_bytes = await file.read()
    csv_text = raw_bytes.decode("utf-8-sig")

    players, messages = parse_ownership_projections_csv(csv_text)
    try:
        file_path = save_projections_csv(settings.nfl_data_dir, season, week, platform, csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return OwnershipProjectionsImportResult(
        file_path=str(file_path),
        season=season,
        week=week,
        player_count=len(players),
        message_counts=dict(Counter(m.level for m in messages)),
        messages=messages,
    )
