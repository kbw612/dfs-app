"""
Ownership schema -- DraftKings salary/ownership-projection data scraped
from oneweekseason.com for a single (season, week), plus the four derived
views computed over it by backend/services/ownership/engine.py: high-owned
("chalk") players, game-leverage groups, pivot groups, and multi-leverage
players (players who qualify under 2+ of the above at once). See that
module's docstring for how each view is computed.

Unlike depth_charts.Snapshot (one team's positions nested under it),
OwnershipSnapshot is a flat list of players -- DK's ownership page has no
natural nesting, and position/team/opponent are just columns on each row.
DST counts as a "position" here rather than a separate list (it was split
out in the original script purely for its own CSV-export convenience).
"""

from typing import Literal, Optional

from pydantic import BaseModel


class OwnershipPlayer(BaseModel):
    player: str
    position: str
    team: str
    opponent: str
    # True if this row's team is playing at the opponent's stadium (the
    # scraped page marks this with an "@" prefix on the Opponent column,
    # e.g. "@HOU" -- stripped here since the bare abbreviation is what
    # every other lookup in this app keys off of, but the distinction
    # itself is still useful to display).
    is_home: Optional[bool] = None
    salary: int
    ownership_pct: float
    # 1-indexed depth-chart rank (e.g. RB1, RB2) -- not part of the
    # ownership source data itself, filled in afterward by cross-referencing
    # the latest depth-chart snapshot by player name (see
    # backend/services/ownership/depth_rank.py). None if there's no
    # depth-chart snapshot yet, or this name doesn't match one -- ownership
    # data still displays fine without it, just without the role label.
    rank: Optional[int] = None


class OwnershipSnapshot(BaseModel):
    scraped_at: str
    source_url: str
    season: int
    week: int
    players: list[OwnershipPlayer]


class GameLeverageGroup(BaseModel):
    """One NFL game (a team + its opponent) that has at least one chalk
    player on either side. `chalk_players` is every high-owned player from
    both teams; `pivot_candidates` is every player from both teams whose
    ownership is currently below the slate's leverage point -- the
    contrarian plays worth pairing against the chalk in this game."""

    team: str
    opponent: str
    chalk_players: list[OwnershipPlayer]
    pivot_candidates: list[OwnershipPlayer]


class PivotGroup(BaseModel):
    """One higher-owned `trigger` player and every same-position,
    similar-salary player who's owned meaningfully less -- see
    compute_pivots() for the exact salary/ownership thresholds."""

    trigger: OwnershipPlayer
    pivots: list[OwnershipPlayer]


class LeverageReason(BaseModel):
    """One concrete reason a player counts toward MultiLeveragePlayer --
    either they're the pivot for a specific higher-owned `against` (kind
    "pivot", from PivotGroup), or they're a contrarian pick against one
    specific chalk player `against` in their game (kind "game", from
    GameLeverageGroup -- `team`/`opponent` identify which game). See
    compute_multi_leverage()."""

    kind: Literal["pivot", "game"]
    against: OwnershipPlayer
    team: Optional[str] = None
    opponent: Optional[str] = None


class MultiLeveragePlayer(BaseModel):
    """A player who's worth fading/pivoting off of 2+ other players at
    once, combining both mechanisms (same-position pivots and game-level
    chalk fades) into one count -- see compute_multi_leverage()."""

    player: OwnershipPlayer
    reasons: list[LeverageReason]


class OwnershipChange(BaseModel):
    """One player's ownership/salary delta between two snapshots of the
    *same* (season, week) -- e.g. two scrapes taken hours apart as news
    breaks, not a week-over-week comparison. Matched by player name alone
    (unlike depth_charts.Change's team+position+name key) since a player's
    team/position are stable within a single week's slate."""

    player: str
    position: str
    team: str
    opponent: str
    change_types: list[Literal["ownership", "salary", "other"]]
    previous_ownership_pct: Optional[float] = None
    current_ownership_pct: Optional[float] = None
    previous_salary: Optional[int] = None
    current_salary: Optional[int] = None
