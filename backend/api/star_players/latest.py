"""
GET /latest (mounted at /api/star-players/latest -- see
backend/api/star_players/__init__.py). Every (team, player) pair
currently flagged as a star player. Never 404s -- an empty list (nothing
starred yet) is a completely normal starting state, not a "you forgot to
retrieve something" precondition the way Vegas Lines'/Weather's/Depth
Charts' own "latest" endpoints treat a missing scrape -- same tolerant
convention as Player Selection's overrides file.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.star_players.star_players_repo import load_star_players
from backend.schemas.star_players.star_players import StarPlayersResult

router = APIRouter()


@router.get("/latest", response_model=StarPlayersResult)
def star_players_latest_endpoint() -> StarPlayersResult:
    return load_star_players(settings.star_players_json)
