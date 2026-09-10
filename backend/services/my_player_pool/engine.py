"""
My Player Pool's own bit of resolution logic -- unlike Player Selection's
default_selected/resolve_selected (backend/services/player_selection/
engine.py), there's no computed default to fall back to here, so this is
just a name for "look this player up in the saved membership map,
treating absence as not-in-the-pool." Kept as a named function anyway so
callers read as intent ("is this player in my pool?") rather than a bare
dict lookup, and so the "absent means False" rule lives in exactly one
place.
"""

from __future__ import annotations


def in_my_player_pool(player: str, membership: dict[str, bool]) -> bool:
    return membership.get(player, False)
