"""
PUT /entry (mounted at /api/player-pool/entry -- see
backend/api/player_pool/__init__.py). Body is a full PlayerPoolEntry --
the edit form always sends every field currently shown (whether changed
or not), so this is a full replace of that (season, week, player)'s saved
scores, not a partial patch (see entries_repo.save_entry). Returns the
saved entry back; the frontend re-fetches GET /latest afterward to pick
up the recomputed total and any carry-forward effects on later weeks
rather than this endpoint duplicating that merge logic.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.player_pool.entries_repo import save_entry
from backend.schemas.player_pool.player_pool import PlayerPoolEntry

router = APIRouter()


@router.put("/entry", response_model=PlayerPoolEntry)
def player_pool_save_entry_endpoint(entry: PlayerPoolEntry) -> PlayerPoolEntry:
    save_entry(settings.player_pool_dir, entry)
    return entry
