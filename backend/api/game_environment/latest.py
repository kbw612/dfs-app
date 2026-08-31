"""
GET /latest?season=&week= (mounted at /api/game-environment/latest -- see
backend/api/game_environment/__init__.py). Every game's saved
Game Environment inputs for that week -- whichever games exist this week
is decided by whoever's calling this (e.g. Player Pool builds its own
game list from the ownership snapshot's players, see
backend/services/player_pool/engine.py), not by this resource, so this
just returns whatever's been saved rather than a fixed list of games.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.game_environment.game_environment_repo import load_game_environment_for_week
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry

router = APIRouter()


class GameEnvironmentLatestResult(BaseModel):
    entries: list[GameEnvironmentEntry]


@router.get("/latest", response_model=GameEnvironmentLatestResult)
def game_environment_latest_endpoint(season: int, week: int) -> GameEnvironmentLatestResult:
    entries = load_game_environment_for_week(settings.game_environment_dir, season, week)
    return GameEnvironmentLatestResult(entries=list(entries.values()))
