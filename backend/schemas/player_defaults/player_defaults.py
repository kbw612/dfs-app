"""
Player Defaults: a player's baseline Volume/Opportunities and Talent/
Explosiveness, set once per (season, player) in Settings' Player Default
Settings grid -- not tied to any specific week.

Player Pool's own per-week Volume/Talent (see backend/schemas/player_pool/
player_pool.py's PlayerPoolEntry) always wins when explicitly saved for
that exact week. When it hasn't been, Player Pool falls back to this
Default, and falls back further to a neutral 2.0 if there's no Default
either (see services/player_pool/engine.py's compute_player_pool). That
replaces the old "carry forward from the most recent earlier week"
behavior entirely -- every Player Pool week is independent now, seeded
from this shared per-season Default rather than whatever the previous
week happened to be scored.

Setting a Default never touches an already-saved PlayerPoolEntry for any
week -- the two resources are only combined at read time, so editing a
player's Default in Settings doesn't retroactively change a week that's
already been explicitly scored.

dfs_type is a separate, unrelated categorization tag on the same
per-(season, player) record -- e.g. "Boom/Bust" -- consumed today by the
Boom/Bust Players tab (see frontend/src/components/BoomBustView.tsx),
which lists every dfs_type="Boom/Bust" player alongside their current
ownership%. Deliberately a plain string, not a Literal/enum, since more
values are expected to be added later purely on the frontend's dropdown
list (frontend/src/components/SettingsView.tsx's DFS_TYPE_OPTIONS) --
constraining it here would mean a backend change for every new category.
None means "no DFS Type set," same not-yet-categorized meaning as
volume/talent being None.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

_Score = Optional[float]


def _score_field() -> _Score:
    return Field(default=None, ge=1.0, le=3.0)


class PlayerDefaultEntry(BaseModel):
    season: int
    player: str

    volume: _Score = _score_field()
    talent: _Score = _score_field()
    dfs_type: Optional[str] = None
