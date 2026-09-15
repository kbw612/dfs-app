"""
GET /optimal-lineup?season=&week=&platform=&contest=&salary_cap= (mounted
at /api/contest-results/optimal-lineup). Not a real contest entry -- the
single highest actual-FPTS DK Classic lineup (1 QB, 2 RB, 3 WR, 1 TE, 1
FLEX, 1 DST) that could have been built under `salary_cap` (default
50000, DK Classic's own cap), computed from this week's Contest Results
player list (same join as /player-results -- see backend/services/
contest_results/contest_results_engine.py's build_contest_result_rows)
via backend/services/contest_results/optimal_lineup.py's
build_optimal_lineup.

Same "both files required" 404 behavior as /top-lineups and
/player-results. 404s separately if no legal roster fits under the cap
at all (e.g. too few salary-matched players at some position).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import load_contest_standings_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.schemas.contest_results.contest_results import OptimalLineup
from backend.services.contest_results.contest_results_engine import build_contest_result_rows
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv
from backend.services.contest_results.optimal_lineup import build_optimal_lineup
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv

router = APIRouter()


@router.get("/optimal-lineup", response_model=OptimalLineup)
def optimal_lineup_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main", salary_cap: int = 50000
) -> OptimalLineup:
    if salary_cap < 1:
        raise HTTPException(status_code=400, detail="salary_cap must be at least 1.")

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

    lineup = build_optimal_lineup(rows, salary_cap)
    if lineup is None:
        raise HTTPException(
            status_code=404,
            detail=f"No legal 9-player lineup fits under a ${salary_cap} salary cap for season {season} week {week}.",
        )
    return lineup
