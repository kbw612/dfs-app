"""
PUT /entry (mounted at /api/player-attributes/entry -- see
backend/api/player_attributes/__init__.py). Body is a full
PlayerAttributeEntry -- Player Pool's grid sends this alongside its own
PUT /api/player-pool/entry whenever a row with a Volume/Talent cell is
saved (see entries_repo.save_entry: a full replace of that (season, week,
player)'s saved Volume/Talent, not a partial patch). Shared by any tab
that wants to read/set a player's Volume/Talent, not specific to Player
Pool.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.player_attributes.entries_repo import save_entry
from backend.schemas.player_attributes.player_attributes import PlayerAttributeEntry

router = APIRouter()


@router.put("/entry", response_model=PlayerAttributeEntry)
def player_attributes_save_entry_endpoint(entry: PlayerAttributeEntry) -> PlayerAttributeEntry:
    save_entry(settings.player_attributes_dir, entry)
    return entry
