"""
GET /games?season=&week=&platform=&contest= (mounted at
/api/schedule/games -- see backend/api/schedule/__init__.py). Backs
Lineup Scenarios' scenario builder, which needs this week's away/home
matchups to let a person check off which team(s) in a game they're
flagging -- the same GameOption list (backend/schemas/game_logs/
game_logs.py) every other Game filter chip in this app already renders
from, computed here via the same build_game_options()/contest_teams
narrowing Game Logs' own endpoint uses (see that module's docstring for
why contest_teams matters: a single-window contest doesn't cover every
real NFL game the league-wide Schedule file has). Empty `games` (not a
404) if the Schedule file hasn't been uploaded yet -- same graceful
degradation as every other Game filter's source.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.schemas.game_logs.game_logs import GameOption
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.game_logs.game_logs_engine import build_game_options
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


class ScheduleGamesResult(BaseModel):
    season: int
    week: int
    games: list[GameOption]


@router.get("/games", response_model=ScheduleGamesResult)
def schedule_games_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"
) -> ScheduleGamesResult:
    schedule_csv = load_schedule_csv(settings.nfl_data_dir, season)
    schedule_rows = parse_schedule_csv(schedule_csv) if schedule_csv is not None else []

    contest_teams: set[str] | None = None
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is not None:
        salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        contest_teams = {p.team for p in salary_snapshot.players}

    games = build_game_options(schedule_rows, week, contest_teams)
    return ScheduleGamesResult(season=season, week=week, games=games)
