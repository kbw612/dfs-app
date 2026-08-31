"""
PUT /entry (mounted at /api/game-environment/entry -- see
backend/api/game_environment/__init__.py). Body is a full
GameEnvironmentEntry, saved once per (season, week, game) -- see
game_environment_repo.save_game_environment. Shared by any tab that wants
to enter/reuse this week's odds, not specific to Player Pool.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.game_environment.game_environment_repo import save_game_environment
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry

router = APIRouter()


@router.put("/entry", response_model=GameEnvironmentEntry)
def game_environment_save_entry_endpoint(entry: GameEnvironmentEntry) -> GameEnvironmentEntry:
    save_game_environment(settings.game_environment_dir, entry)
    return entry
