"""
GET /player-results?season=&week=&platform=&contest= (mounted at
/api/contest-results/player-results). This week's uploaded contest
standings' own player-reference table (every distinct player+roster-slot
combination that appeared anywhere in the contest), reformatted with
Salary joined in from the week's DK salary file -- see
backend/services/contest_results/contest_results_engine.py's
build_contest_result_rows.

`contest` (default "Classic Main", the same Settings chip value used
everywhere else -- see SettingsView.tsx) picks which contest's Contest
Standings/Salary File get loaded -- see backend/repositories/
contest_results/contest_standings_repo.py and backend/repositories/
dk_salary/salary_snapshot_repo.py for the filenames each one resolves to.

Same "both files required" 404 behavior as /top-lineups.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import load_contest_standings_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.schemas.contest_results.contest_results import ContestResultRow
from backend.services.contest_results.contest_results_engine import build_contest_result_rows
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv

router = APIRouter()


class ContestResultRowsResult(BaseModel):
    rows: list[ContestResultRow]


@router.get("/player-results", response_model=ContestResultRowsResult)
def player_results_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"
) -> ContestResultRowsResult:
    standings_csv = load_contest_standings_csv(settings.nfl_data_dir, season, week, platform, contest)
    if standings_csv is None:
        raise HTTPException(
            status_code=404,
            detail=f"No contest standings uploaded yet for season {season} week {week} -- upload it in the Settings tab.",
        )
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is None:
        raise HTTPException(
            status_code=404,
            detail=f"No DK salary file uploaded yet for season {season} week {week} -- upload it in the Settings tab.",
        )

    standings = parse_contest_standings_csv(standings_csv)
    salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)

    rows = build_contest_result_rows(standings, salary_snapshot.players, week)
    return ContestResultRowsResult(rows=rows)
