"""
GET /list?season=&platform=&week= (mounted at /api/dk-players/list -- see
backend/api/dk_players/__init__.py). Returns the season-long tracker,
optionally narrowed to one `week` -- omit it to get every week loaded so
far (the "All" chip in the DK Players tab). Empty list (not 404) if
nothing's been added for this season/platform yet -- an empty tracker is a
normal starting state, not an error.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.schemas.dk_players.dk_players import DkPlayersResult
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv

router = APIRouter()


@router.get("/list", response_model=DkPlayersResult)
def list_dk_players_endpoint(season: int, platform: str = "DraftKings", week: int | None = None) -> DkPlayersResult:
    csv_text = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    rows = parse_dk_players_csv(csv_text) if csv_text is not None else []
    if week is not None:
        rows = [row for row in rows if row.week == week]
    return DkPlayersResult(season=season, platform=platform, players=rows)
