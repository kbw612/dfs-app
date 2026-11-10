"""
The "<1% owned" filter shared by the Ownership Summary, Ownership Pivots,
Leverage & Pivots and Game Preview. OWS shows every QB and DST whatever
their ownership, so only RB, WR and TE are ever hidden: those owned below
`cutoff` percent (the "<1%" placeholder, and any real value under the
cutoff). A player with no ownership entry is never hidden. Cutoff 0 hides
nobody.
"""

from __future__ import annotations

from backend.schemas.ownership.ownership import OwnershipPlayer

HIDEABLE_POSITIONS = {"RB", "WR", "TE"}
DEFAULT_CUTOFF = 1.0


def hide_below_cutoff(players: list[OwnershipPlayer], cutoff: float) -> list[OwnershipPlayer]:
    if cutoff <= 0:
        return players
    return [
        p
        for p in players
        if not (p.position in HIDEABLE_POSITIONS and p.ownership_pct is not None and p.ownership_pct < cutoff)
    ]
