"""
GET /multipliers?season=&week=&platform=&contest=&trailing_weeks= (mounted
at /api/multipliers -- see backend/api/multipliers/__init__.py). Backs the
Multipliers tab -- see backend/services/multipliers/multipliers_engine.py
for the full computation. Same tracker + Schedule + contest_teams loading
pattern as backend/api/game_logs/game_logs.py's own endpoint (this tab
needs none of Game Logs' extra FantasyData weekly-stats/usage-share
inputs, since Touches/Targets/etc. aren't part of this tab at all).

404 only if the DK Players tracker has no rows at all yet for this
(season, platform) -- same "nothing to show at all" case as Game Logs.
Every other missing side-channel (no Schedule file, no Salary File for
this contest yet) degrades gracefully -- see build_multiplier_rows' own
docstring.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.schemas.multipliers.multipliers import MultipliersResult
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.game_logs.game_logs_engine import build_game_options
from backend.services.multipliers.multipliers_engine import build_multiplier_rows
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


@router.get("/multipliers", response_model=MultipliersResult)
def multipliers_endpoint(
    season: int, week: int, platform: str = "DraftKings", trailing_weeks: int = 5, contest: str = "Classic Main"
) -> MultipliersResult:
    tracker_csv = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    if tracker_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No DK Players tracker started yet for season {season} -- "
                'run "Add Week Players" on the DK Players tab first.'
            ),
        )
    tracker_rows = parse_dk_players_csv(tracker_csv)

    schedule_csv = load_schedule_csv(settings.nfl_data_dir, season)
    schedule_rows = parse_schedule_csv(schedule_csv) if schedule_csv is not None else []

    contest_teams: set[str] | None = None
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is not None:
        salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        contest_teams = {p.team for p in salary_snapshot.players}

    rows, base_week = build_multiplier_rows(tracker_rows, schedule_rows, week, trailing_weeks, contest_teams)
    games = build_game_options(schedule_rows, base_week, contest_teams)

    return MultipliersResult(
        season=season,
        week=week,
        base_week=base_week,
        trailing_weeks=trailing_weeks,
        games=games,
        rows=rows,
    )
