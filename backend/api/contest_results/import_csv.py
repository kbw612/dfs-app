"""
POST /import-csv?season=&week=&platform= (mounted at
/api/contest-results/import-csv -- see backend/api/contest_results/
__init__.py). Multipart upload of DraftKings' own contest standings
export (see backend/services/contest_results/contest_standings_parser.py
for the column shape this expects -- a different file than the DK salary
export, and a different upload than backend/api/dk_salary/import_csv.py).
Parses it once here just to report entry_count/reference_row_count back
to the caller, then saves the raw CSV text as-is via
contest_standings_repo -- same "always overwritten, re-parsed fresh on
every read" convention as DK Salary's own import-csv.
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import save_contest_standings_csv
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv

router = APIRouter()


class ContestStandingsImportResult(BaseModel):
    snapshot_path: str
    season: int
    week: int
    entry_count: int
    reference_row_count: int


@router.post("/import-csv", response_model=ContestStandingsImportResult)
async def import_contest_standings_csv_endpoint(
    season: int,
    week: int,
    file: UploadFile = File(...),
    platform: str = "DraftKings",
    contest: str = "Classic Main",
) -> ContestStandingsImportResult:
    raw_bytes = await file.read()
    # utf-8-sig strips a leading byte-order-mark if the export included
    # one -- harmless no-op on a file that doesn't have one, same as
    # DK Salary's own import-csv.
    csv_text = raw_bytes.decode("utf-8-sig")

    standings = parse_contest_standings_csv(csv_text)
    file_path = save_contest_standings_csv(settings.nfl_data_dir, season, week, platform, contest, csv_text)

    return ContestStandingsImportResult(
        snapshot_path=str(file_path),
        season=season,
        week=week,
        entry_count=len(standings.entries),
        reference_row_count=len(standings.reference_rows),
    )
