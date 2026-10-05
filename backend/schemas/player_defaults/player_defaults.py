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

dfs_types is a separate, unrelated set of categorization tags on the same
per-(season, player) record -- a player can carry any combination of them
at once (e.g. both "Boom/Bust" and "Standalone"), unlike Volume/Talent
which are each a single value. "Boom/Bust" is consumed today by the
Boom/Bust Players tab (see frontend/src/components/BoomBustView.tsx),
which lists every player whose dfs_types includes "Boom/Bust" alongside
their current ownership%. "Standalone" marks a player who's fine to roster
without anyone else from his own game (including either QB) -- not
enforced anywhere yet; the intended future use is a lineup-optimizer
validator that flags a non-Standalone player rostered with nobody else
from their game (see Player Rankings' own `standalone` column in
backend/schemas/player_pool/player_pool.py, which starts from whichever of
these tags apply here and can be overridden per week).

Deliberately a plain list of strings, not a Literal/enum, since more tags
are expected to be added later purely on the frontend's checkbox list
(frontend/src/dfsTypes.ts's DFS_TYPE_OPTIONS) -- constraining it here would
mean a backend change for every new category. An empty list means "no DFS
Type set," same not-yet-categorized meaning as volume/talent being None.
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
    dfs_types: list[str] = Field(default_factory=list)
