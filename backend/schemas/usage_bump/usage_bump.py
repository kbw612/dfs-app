"""
UsageBump schema -- one record per (healthy) player who benefits from a
teammate's non-null status, per compute_usage_bumps() (Section: derived
analysis over a single depth-chart snapshot, not a diff between two).

No severity/priority weighting baked into the schema itself, same
philosophy as Change (backend/schemas/depth_charts/change.py): this just
reports the computed bump_score and what caused it. `causes` is always
non-empty (a UsageBump only exists because something contributed to
its score).
"""

from typing import Literal, Optional

from pydantic import BaseModel


class UsageBumpListEntry(BaseModel):
    """One (real) member of a trigger's resolved usage-bump list -- see
    UsageBumpCause.usage_bump_list. `depth` is the 1-indexed position
    within *that list* (not the player's real depth-chart rank), matching
    the keys used in config/player-out-settings.json's bump_depth_values.
    `weight` is that matched row's value for this depth -- what would
    apply to this player if they're currently healthy, and what's
    withheld if they're currently out too (see engine.py). `position` and
    `rank` are this player's own real position group and depth-chart rank
    (lists can span positions, e.g. an RB1 trigger's list can include WRs
    and a TE) -- same shape as UsageBump.position/rank, so the frontend
    can render a role label like "WR1" the same way it already does for
    the top-level UsageBump. `status` is their current status, or None
    if they're healthy."""

    depth: int
    player: str
    position: str
    rank: int
    status: Optional[str] = None
    weight: float


class UsageBumpCause(BaseModel):
    player: str
    status: str  # always non-null -- this is what made them a "cause"
    # This trigger's own real position and depth-chart rank -- same shape
    # as UsageBump.position/rank, so a role label like "WR2" renders the
    # same way for the trigger as it does for a beneficiary.
    position: str
    rank: int
    # From config/player-out-settings.json's scoring matrix -- fractional
    # (e.g. 0.25, 1.5), not a flat per-injury count. See
    # backend/services/usage_bump/engine.py for how it's computed.
    weight: float
    # The exact combination of list-positions (1-indexed) that were also
    # out -- matches config/player-out-settings.json's `player_out_depths`
    # field both in name and in shape, since this is literally the key
    # that was looked up there. [0] is the sentinel for "nobody else in
    # the list is out."
    player_out_depths: list[int]
    # This trigger's full resolved usage-bump list (real, on-roster
    # players only, capped at 5) -- every player in it, not just the one
    # this cause is attached to, so the full scoring-matrix row is
    # visible for any of them.
    usage_bump_list: list[UsageBumpListEntry]
    # How this trigger's usage-bump list was resolved -- see engine.py's
    # module docstring for the two-tier priority order.
    source: Literal["curated", "position-settings"]
    # Only set when source == "position-settings": the role label that was
    # looked up (e.g. "WR2") and its configured usageBumpPositions list,
    # verbatim from config/usage-bump-position-settings.json -- role
    # labels, not resolved player names (that's usage_bump_list).
    source_role_label: Optional[str] = None
    source_role_positions: Optional[list[str]] = None


class UsageBump(BaseModel):
    team_abbrev: Optional[str] = None
    position: str
    player: str
    rank: int  # 1-indexed, this player's own position in their position's array
    bump_score: float
    causes: list[UsageBumpCause]
