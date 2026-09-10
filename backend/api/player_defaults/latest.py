"""
GET /latest?season= (mounted at /api/player-defaults/latest -- see
backend/api/player_defaults/__init__.py). Every player's saved Player
Default for that season -- no week parameter, since Defaults aren't a
per-week concept (see backend/schemas/player_defaults/
player_defaults.py). Just mirrors whatever's on disk, the same
"echo what's saved" shape as GET /api/game-environment/latest.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.player_defaults.defaults_repo import load_defaults_for_season
from backend.schemas.player_defaults.player_defaults import PlayerDefaultEntry

router = APIRouter()


class PlayerDefaultsLatestResult(BaseModel):
    defaults: list[PlayerDefaultEntry]


@router.get("/latest", response_model=PlayerDefaultsLatestResult)
def player_defaults_latest_endpoint(season: int) -> PlayerDefaultsLatestResult:
    defaults = load_defaults_for_season(settings.nfl_data_dir, season)
    return PlayerDefaultsLatestResult(defaults=list(defaults.values()))
