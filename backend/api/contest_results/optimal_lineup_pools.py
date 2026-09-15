"""
GET /optimal-lineups-top10 (mounted at
/api/contest-results/optimal-lineups-top10) --
season=&week=&platform=&contest=&salary_cap=&regenerate=. Backs the
Contest Results tab's collapsible "Optimal Lineups" panel: a pool of the
10 exact highest-scoring distinct (not real-contest-entry) lineups,
built from this week's Contest Results player list -- see backend/
services/contest_results/lineup_generators.py's build_top10_by_points
for the generation algorithm.

Cached to disk the first time it's generated for a given (season, week,
platform, contest) -- see backend/repositories/contest_results/
optimal_lineups_cache_repo.py -- since generating it is meaningfully
more expensive than the single-lineup /optimal-lineup endpoint (it's
effectively many constrained re-solves, not just one). A page visit
reads the cached file if it's already there; pass `regenerate=true` to
force a fresh generation (overwriting the cache) -- e.g. after
re-running Calculate Week Points with corrected stats.

Same "both files required" 404 behavior as /top-lineups and
/player-results. Also 404s if no legal lineup fits under the cap at all
(same as /optimal-lineup).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import load_contest_standings_csv
from backend.repositories.contest_results.optimal_lineups_cache_repo import load_top10_by_points, save_top10_by_points
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.schemas.contest_results.contest_results import ContestResultRow, OptimalLineup
from backend.services.contest_results.contest_results_engine import build_contest_result_rows
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv
from backend.services.contest_results.lineup_generators import build_top10_by_points
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv

router = APIRouter()


class OptimalLineupsResult(BaseModel):
    lineups: list[OptimalLineup]


def _load_contest_result_rows(season: int, week: int, platform: str, contest: str) -> list[ContestResultRow]:
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
    return build_contest_result_rows(standings, salary_snapshot.players, week)


@router.get("/optimal-lineups-top10", response_model=OptimalLineupsResult)
def optimal_lineups_top10_endpoint(
    season: int,
    week: int,
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    salary_cap: int = 50000,
    regenerate: bool = False,
) -> OptimalLineupsResult:
    if not regenerate:
        cached = load_top10_by_points(settings.nfl_data_dir, season, week, platform, contest)
        if cached is not None:
            return OptimalLineupsResult(lineups=cached)

    rows = _load_contest_result_rows(season, week, platform, contest)
    lineups = build_top10_by_points(rows, salary_cap)
    if not lineups:
        raise HTTPException(
            status_code=404,
            detail=f"No legal 9-player lineup fits under a ${salary_cap} salary cap for season {season} week {week}.",
        )
    save_top10_by_points(settings.nfl_data_dir, season, week, platform, contest, lineups)
    return OptimalLineupsResult(lineups=lineups)
