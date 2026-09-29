"""
PUT /entry (mounted at /api/star-players/entry -- see
backend/api/star_players/__init__.py). Sets or clears one (team, player)
pair's star flag -- the Depth Charts tab's star icon sends this
immediately on click (see star_players_repo.set_star_player: only that
one pair is touched, every other starred player is left alone). Returns
the full updated list so the frontend can refresh its local state from
the server's own echo rather than assuming its optimistic update matched.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.star_players.star_players_repo import set_star_player
from backend.schemas.star_players.star_players import StarPlayersResult

router = APIRouter()


class StarPlayerEntryInput(BaseModel):
    team: str
    player: str
    starred: bool


@router.put("/entry", response_model=StarPlayersResult)
def star_players_save_entry_endpoint(entry: StarPlayerEntryInput) -> StarPlayersResult:
    return set_star_player(settings.star_players_json, entry.team, entry.player, entry.starred)
