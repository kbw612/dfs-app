"""
GET /top-patterns?season=&weeks=&platform=&contest=&top_n= (mounted at
/api/lineup-scenarios/top-patterns). Counts the generic stack/flex/DST/
salary patterns used by the top `top_n` finishing lineups of each requested
week's uploaded contest standings -- see backend/services/lineup_scenarios/
top_lineup_patterns.py for exactly what is counted and how.

`weeks` is a comma-separated list (default "1,2,3,4"). A week missing its
contest standings or DK salary file is skipped and reported in
`weeks_missing` rather than failing the whole request -- the analysis is
still useful across the weeks that do exist. 404 only when NO requested
week has both files.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import load_contest_standings_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.lineup_scenarios.top_lineup_patterns import (
    TopLineupPatternsResult,
    WeekInput,
    analyze_top_lineups,
)

router = APIRouter()


@router.get("/top-patterns", response_model=TopLineupPatternsResult)
def top_patterns_endpoint(
    season: int,
    weeks: str = "1,2,3,4",
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    top_n: int = 1000,
) -> TopLineupPatternsResult:
    if top_n < 1:
        raise HTTPException(status_code=400, detail="top_n must be at least 1.")
    try:
        week_list = sorted({int(w) for w in weeks.split(",") if w.strip()})
    except ValueError:
        raise HTTPException(status_code=400, detail="weeks must be a comma-separated list of week numbers.")
    if not week_list:
        raise HTTPException(status_code=400, detail="weeks must include at least one week.")

    week_inputs: list[WeekInput] = []
    missing: list[int] = []
    for week in week_list:
        standings_csv = load_contest_standings_csv(settings.nfl_data_dir, season, week, platform, contest)
        salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
        if standings_csv is None or salary_csv is None:
            missing.append(week)
            continue
        salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        week_inputs.append(
            WeekInput(
                week=week,
                standings=parse_contest_standings_csv(standings_csv),
                salary_players=salary_snapshot.players,
            )
        )

    if not week_inputs:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No week in {week_list} has both contest standings and a DK salary file uploaded for "
                f"season {season} -- upload them in the Settings tab."
            ),
        )

    return analyze_top_lineups(week_inputs, top_n, weeks_missing=missing)
