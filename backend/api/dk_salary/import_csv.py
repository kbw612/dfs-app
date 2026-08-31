"""
POST /import-csv?season=&week=&platform= (mounted at
/api/dk-salary/import-csv -- see backend/api/dk_salary/__init__.py).
Multipart file upload of DK's own native salary export -- see
backend/services/dk_salary/dk_salary_loader.py for the column shape this
expects. Parses it once here just to report player_count/messages back to
the caller, then saves the *raw* CSV text as-is via salary_snapshot_repo
(see that module's docstring -- there's only ever one current file per
(season, week, platform), always overwritten, no JSON conversion). Shared
by Salary Blocks and Player Pool -- uploading once here feeds both tabs'
GET /latest endpoints, which re-parse the raw file fresh on every read.

`platform` (default "DraftKings", the only one with a real file format
behind it today) picks the filename prefix -- see
backend/services/platform_settings/prefix.py. Settings sends whichever
platform is currently selected in its top panel (see
frontend/src/components/SettingsView.tsx).
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import save_salary_csv
from backend.schemas.depth_charts.snapshot import Message
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv

router = APIRouter()


class DkSalaryImportResult(BaseModel):
    snapshot_path: str
    scraped_at: str
    season: int
    week: int
    player_count: int
    message_counts: dict[str, int]
    messages: list[Message]


@router.post("/import-csv", response_model=DkSalaryImportResult)
async def import_dk_salary_csv_endpoint(
    season: int, week: int, file: UploadFile = File(...), platform: str = "DraftKings"
) -> DkSalaryImportResult:
    raw_bytes = await file.read()
    # utf-8-sig strips a leading byte-order-mark if Excel/DK's own export
    # included one -- harmless no-op on a file that doesn't have one.
    csv_text = raw_bytes.decode("utf-8-sig")

    snapshot, messages = parse_dk_salary_csv(csv_text, season, week)
    try:
        file_path = save_salary_csv(settings.nfl_data_dir, season, week, platform, csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DkSalaryImportResult(
        snapshot_path=str(file_path),
        scraped_at=snapshot.scraped_at,
        season=snapshot.season,
        week=snapshot.week,
        player_count=len(snapshot.players),
        message_counts=dict(Counter(m.level for m in messages)),
        messages=messages,
    )
