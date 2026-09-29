"""
POST /upload?season=&week=&platform=&contest= (mounted at
/api/lineup-scenarios/upload -- see backend/api/lineup_scenarios/
__init__.py). Multipart upload of a person's own already-built lineups
export from an external optimizer -- see backend/services/
lineup_scenarios/lineup_upload_parser.py for the column shape this
expects (a header row of roster position labels, then one row per
lineup). Parses it once here just to report lineup_count/
roster_positions back to the caller, then saves the raw CSV text as-is
via lineup_upload_repo -- same "always overwritten, re-parsed fresh on
every read" convention as every other CSV upload in this app (e.g.
Contest Standings' own import-csv).
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.lineup_scenarios.lineup_upload_repo import save_lineup_upload_csv
from backend.services.lineup_scenarios.lineup_upload_parser import parse_lineup_upload_csv

router = APIRouter()


class LineupScenarioUploadResult(BaseModel):
    lineup_count: int
    roster_positions: list[str]


@router.post("/upload", response_model=LineupScenarioUploadResult)
async def upload_lineup_scenarios_csv_endpoint(
    season: int,
    week: int,
    file: UploadFile = File(...),
    platform: str = "DraftKings",
    contest: str = "Classic Main",
) -> LineupScenarioUploadResult:
    raw_bytes = await file.read()
    # utf-8-sig strips a leading byte-order-mark if the export included
    # one -- harmless no-op otherwise, same as every other CSV upload in
    # this app.
    csv_text = raw_bytes.decode("utf-8-sig")

    lineups = parse_lineup_upload_csv(csv_text)
    roster_positions = [p.roster_position for p in lineups[0].players] if lineups else []
    save_lineup_upload_csv(settings.nfl_data_dir, season, week, platform, contest, csv_text)

    return LineupScenarioUploadResult(lineup_count=len(lineups), roster_positions=roster_positions)
