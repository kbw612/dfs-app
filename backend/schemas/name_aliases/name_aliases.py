"""
Name Aliases -- a small, global (not per-season/week) list of alias ->
canonical player-name pairs, e.g. "James Cook III" -> "James Cook",
maintained by hand in Settings (see backend/repositories/name_aliases/
name_aliases_repo.py). Applied wherever DK Players (backend/services/
dk_players/dk_players_engine.py) matches names across the Salary File,
weekly FantasyData stat files, and Contest Standings -- three independent
DK/third-party exports that don't always spell a name identically.
"""

from __future__ import annotations

from pydantic import BaseModel


class NameAlias(BaseModel):
    alias: str
    canonical: str


class NameAliasesResult(BaseModel):
    aliases: list[NameAlias]
