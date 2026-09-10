"""
GET /week-status?season=&week=&platform= (mounted at
/api/dk-players/week-status). Lets the frontend check whether a week
already has rows (and whether they already have calculated points) BEFORE
calling POST /add-week, so the "replace week N?" confirm dialog can be
worded accurately -- see backend/services/dk_players/dk_players_engine.py's
week_status().
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.schemas.dk_players.dk_players import DkPlayersWeekStatus
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv
from backend.services.dk_players.dk_players_engine import week_status

router = APIRouter()


@router.get("/week-status", response_model=DkPlayersWeekStatus)
def dk_players_week_status_endpoint(season: int, week: int, platform: str = "DraftKings") -> DkPlayersWeekStatus:
    csv_text = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    rows = parse_dk_players_csv(csv_text) if csv_text is not None else []
    return week_status(rows, week)
