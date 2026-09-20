"""
GET/PUT /api/usage-bump-players -- the hand-curated Usage Bump Players
list (backend/schemas/usage_bump/usage_bump_players.py), edited from its
own top-level tab (frontend/src/components/UsageBumpPlayersView.tsx), read
by compute_usage_bumps() (backend/services/usage_bump/engine.py) via
usage_bump_players_repo.load_usage_bump_players's flattened view of this
same file. PUT always replaces the whole list, same "caller sends the
complete current set" convention as Name Aliases' own save.

Mounted at its own top-level path (not nested under "/opportunities",
GET /opportunities/latest's own prefix) -- this is a distinct resource
(hand-curated config) from that endpoint's computed results, same
reasoning Name Aliases gets its own "/api/name-aliases" rather than living
under whichever feature happens to consume it.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.usage_bump.usage_bump_players_repo import (
    load_usage_bump_players_file,
    save_usage_bump_players_file,
)
from backend.schemas.usage_bump.usage_bump_players import UsageBumpPlayersResult

router = APIRouter(prefix="/usage-bump-players")


@router.get("", response_model=UsageBumpPlayersResult)
def get_usage_bump_players_endpoint() -> UsageBumpPlayersResult:
    return load_usage_bump_players_file(settings.usage_bump_players_json)


@router.put("", response_model=UsageBumpPlayersResult)
def put_usage_bump_players_endpoint(body: UsageBumpPlayersResult) -> UsageBumpPlayersResult:
    save_usage_bump_players_file(settings.usage_bump_players_json, body)
    return body
