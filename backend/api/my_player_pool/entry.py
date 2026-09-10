"""
PUT /entry (mounted at /api/my-player-pool/entry -- see
backend/api/my_player_pool/__init__.py). Body is a full
MyPlayerPoolEntryInput -- saves one player's explicit in_pool state for
that (season, week, platform, contest), overwriting whatever was saved
before for that player. Called both by the checkbox column on the Player
Rankings grid and by the search-and-add box on the My Player Pool tab
itself (see frontend/src/components/PlayerPoolView.tsx and
MyPlayerPoolView.tsx) -- no debounce, since both are single discrete
actions (a checkbox click or an Add/Remove button), same as Player
Selection's own entry endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.my_player_pool.my_player_pool_repo import save_membership
from backend.schemas.my_player_pool.my_player_pool import MyPlayerPoolEntryInput

router = APIRouter()


@router.put("/entry", response_model=MyPlayerPoolEntryInput)
def my_player_pool_entry_endpoint(entry: MyPlayerPoolEntryInput) -> MyPlayerPoolEntryInput:
    save_membership(
        settings.nfl_data_dir, entry.season, entry.week, entry.platform, entry.contest, entry.player, entry.in_pool
    )
    return entry
