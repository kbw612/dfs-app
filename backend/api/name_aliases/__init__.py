"""
GET/PUT /api/name-aliases -- the global Name Aliases list (backend/schemas/
name_aliases/name_aliases.py), maintained by hand in Settings and applied
by DK Players' calculate_week_points() when matching player names across
the Salary File, weekly FantasyData stat files, and Contest Standings.
PUT always replaces the whole list, same "caller sends the complete
current set" convention as Player Defaults' own save.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.name_aliases.name_aliases_repo import load_name_aliases, save_name_aliases
from backend.schemas.name_aliases.name_aliases import NameAlias, NameAliasesResult

router = APIRouter(prefix="/name-aliases")


@router.get("", response_model=NameAliasesResult)
def get_name_aliases_endpoint() -> NameAliasesResult:
    return NameAliasesResult(aliases=load_name_aliases(settings.name_aliases_json))


@router.put("", response_model=NameAliasesResult)
def put_name_aliases_endpoint(body: NameAliasesResult) -> NameAliasesResult:
    aliases: list[NameAlias] = body.aliases
    save_name_aliases(settings.name_aliases_json, aliases)
    return NameAliasesResult(aliases=aliases)
