"""
PUT /entry (mounted at /api/player-selection/entry -- see
backend/api/player_selection/__init__.py). Body is a full
PlayerSelectionOverride -- saves one player's explicit selected/unselected
state for that (season, week, platform), overwriting whatever was saved
before for that player. The grid in Settings calls this immediately on
every checkbox toggle (see frontend/src/components/PlayerSelectionGrid.tsx)
-- no debounce, since a checkbox click is already a single discrete edit.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.player_selection.player_selection_repo import save_override
from backend.schemas.player_selection.player_selection import PlayerSelectionOverride

router = APIRouter()


@router.put("/entry", response_model=PlayerSelectionOverride)
def player_selection_entry_endpoint(entry: PlayerSelectionOverride) -> PlayerSelectionOverride:
    save_override(settings.nfl_data_dir, entry.season, entry.week, entry.platform, entry.player, entry.selected)
    return entry
