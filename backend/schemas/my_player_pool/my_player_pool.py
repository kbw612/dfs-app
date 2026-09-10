"""
My Player Pool: a personal, opt-in shortlist of players for this
(season, week, platform) -- the players someone's planning to feed into
an external optimizer lineup tool, not a narrowing/filtering mechanism
like Settings' Player Selection grid. The two are deliberately
independent: a player can be added here whether or not they're checked
in Player Selection, and vice versa (see backend/api/my_player_pool/
latest.py).

`in_pool` has no computed default the way Player Selection's `selected`
does (see backend/services/player_selection/engine.py's default_selected)
-- every player starts out simply absent from the pool, and only shows up
on the My Player Pool tab once explicitly added (see
backend/services/my_player_pool/engine.py). Scoped to (season, week,
platform, contest), same as the salary file itself -- there's no
carry-forward from an earlier week or another contest, so each new
week's (or contest's) pool starts empty.

The read side (GET /api/my-player-pool/latest) reuses
backend/schemas/player_pool/player_pool.py's PlayerPoolResult directly
rather than defining a parallel row schema -- a My Player Pool row is
exactly a Player Pool row (same salary, Total, and every score field),
just drawn from a different, independent membership list instead of
Player Selection's.
"""

from __future__ import annotations

from pydantic import BaseModel


class MyPlayerPoolEntryInput(BaseModel):
    season: int
    week: int
    platform: str = "DraftKings"
    contest: str = "Classic Main"
    player: str
    in_pool: bool
