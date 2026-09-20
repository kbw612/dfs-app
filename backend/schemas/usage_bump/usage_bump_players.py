"""
Editable shape of data/nfl/2026/usage_bump_players.json -- the hand-
curated "if this trigger player is out, these named teammates get bumped
usage" list (see backend/repositories/usage_bump/usage_bump_players_repo.py
and backend/services/usage_bump/engine.py for how it's actually consumed).
This schema backs the Usage Bump Players tab's own GET/PUT
/api/usage-bump-players (backend/api/usage_bump/players.py) -- unlike
`load_usage_bump_players`'s flattened dict (built for the engine's own
lookup-by-(team, name) access pattern), this preserves the file's real
nested shape (team -> players -> ordered beneficiary list) so the editor
can render and re-save it faithfully, including `moreUsagePlayers`' own
priority order.

Field names are camelCase (teamAbbrev, moreUsagePlayers), matching the
file's own on-disk keys exactly rather than this codebase's usual
snake_case -- this file's format predates this schema and already has
real hand-curated data in it (see usage_bump_players_repo.py's own
docstring), so the schema mirrors the existing keys rather than the other
way around.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UsageBumpPlayerEntry(BaseModel):
    name: str
    # Ordered by priority -- first name is the biggest beneficiary. Capped
    # at 5 usable entries by the engine (backend/services/usage_bump/
    # engine.py), but not enforced here -- the editor is free to hold more
    # while someone's still reordering/curating, same "storage doesn't
    # enforce what only the consumer cares about" spirit as everywhere
    # else in this app.
    moreUsagePlayers: list[str] = Field(default_factory=list)


class UsageBumpTeamEntry(BaseModel):
    teamAbbrev: str
    players: list[UsageBumpPlayerEntry] = Field(default_factory=list)


class UsageBumpPlayersResult(BaseModel):
    teams: list[UsageBumpTeamEntry] = Field(default_factory=list)
