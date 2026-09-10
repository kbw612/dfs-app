"""
PUT /entry (mounted at /api/player-defaults/entry -- see
backend/api/player_defaults/__init__.py). Body is a full
PlayerDefaultEntry -- Settings' Player Default Settings grid sends this
whenever a player's Volume/Talent Default cell is saved (see
defaults_repo.save_default: a full replace of that (season, player)'s
saved Default, not a partial patch). Distinct from PUT
/api/player-pool/entry -- that one saves a specific week's explicit
Volume/Talent, this one saves the player-level fallback Player Pool uses
when a week has no explicit save of its own.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.player_defaults.defaults_repo import save_default
from backend.schemas.player_defaults.player_defaults import PlayerDefaultEntry

router = APIRouter()


@router.put("/entry", response_model=PlayerDefaultEntry)
def player_defaults_save_entry_endpoint(entry: PlayerDefaultEntry) -> PlayerDefaultEntry:
    save_default(settings.nfl_data_dir, entry)
    return entry
