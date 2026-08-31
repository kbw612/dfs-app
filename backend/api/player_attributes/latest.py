"""
GET /latest?season=&week= (mounted at /api/player-attributes/latest --
see backend/api/player_attributes/__init__.py). Every player's explicitly
saved Volume/Talent for that exact week -- not carry-forward-resolved,
since resolving requires a specific player and field (see
entries_repo.resolve_carry_forward_value), which needs a caller who
already knows which players it cares about (e.g. Player Pool's engine,
which calls resolve_carry_forward_value directly in-process rather than
through this endpoint). This just mirrors whatever's been saved, the same
"echo what's on disk" shape as GET /api/game-environment/latest.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.player_attributes.entries_repo import load_entries_for_week
from backend.schemas.player_attributes.player_attributes import PlayerAttributeEntry

router = APIRouter()


class PlayerAttributesLatestResult(BaseModel):
    entries: list[PlayerAttributeEntry]


@router.get("/latest", response_model=PlayerAttributesLatestResult)
def player_attributes_latest_endpoint(season: int, week: int) -> PlayerAttributesLatestResult:
    entries = load_entries_for_week(settings.player_attributes_dir, season, week)
    return PlayerAttributesLatestResult(entries=list(entries.values()))
