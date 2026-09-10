"""
GET /top-lineups?season=&week=&platform=&top_n= (mounted at
/api/contest-results/top-lineups). The first `top_n` entries (by the
export's own row order, which is already rank-ascending -- see
contest_standings_parser.py) from this week's uploaded contest standings,
each exploded into its 9 players and joined against the week's DK salary
file for Salary/true Position and Exp Pts (a fixed salary * 4 / 1000 --
see contest_results_engine.py's EXP_PTS_MULTIPLIER for why this is its
own constant rather than Settings' Salary Multiplier field), plus the
export's own %Drafted/Act Pts for each player -- see backend/services/
contest_results/contest_results_engine.py's build_top_lineups for exactly
how that join works and what happens when a player doesn't match.

Requires both this week's contest standings AND its DK salary file to
already be uploaded -- 404s (naming whichever's missing) if either isn't
there yet, same pattern as /api/ownership/position-blocks.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import load_contest_standings_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.schemas.contest_results.contest_results import TopLineup
from backend.services.contest_results.contest_results_engine import build_top_lineups
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv

router = APIRouter()


class TopLineupsResult(BaseModel):
    lineups: list[TopLineup]


@router.get("/top-lineups", response_model=TopLineupsResult)
def top_lineups_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main", top_n: int = 10
) -> TopLineupsResult:
    if top_n < 1:
        raise HTTPException(status_code=400, detail="top_n must be at least 1.")

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

    lineups = build_top_lineups(standings, salary_snapshot.players, top_n)
    return TopLineupsResult(lineups=lineups)
