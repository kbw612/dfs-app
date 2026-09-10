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
    # None means ownership isn't known yet -- ownership projections are
    # only available later in the week (see csv_loader.py's docstring),
    # while salary/position/team data can be loaded as soon as DK
    # publishes the slate. Every view that ranks/filters by ownership
    # (compute_high_owned, compute_game_leverage, compute_pivots) treats a
    # None here as "can't classify this player, leave them out" rather
    # than raising or defaulting to 0 -- see engine.py.
    ownership_pct: Optional[float] = None
    # 1-indexed depth-chart position (e.g. RB1, RB2) -- not part of the
    # ownership source data itself, filled in afterward by cross-referencing
    # the latest depth-chart snapshot by player name (see
    # backend/services/ownership/depth_rank.py). None if there's no
    # depth-chart snapshot yet, or this name doesn't match one -- ownership
    # data still displays fine without it, just without the role label.
    # Named depth_rank (not rank) to avoid colliding with the Player
    # Rankings tab's Total-based score ranking, which is a wholly
    # different concept -- this is a fixed depth-chart slot, not a
    # computed quality score.
    depth_rank: Optional[int] = None
    # Resolved Salary Multiplier * salary / 1000 (see backend/services/
    # salary_multiplier/engine.py) -- None everywhere OwnershipPlayer is
    # used except Salary Blocks (backend/api/ownership/position_blocks.py),
    # the only caller that currently resolves a platform's multiplier
    # before building these. Left as an optional add-on rather than a
    # required field so every other OwnershipPlayer consumer (Ownership
    # tab, leverage/pivot views, the raw DK salary snapshot) is unaffected.
    expected_fpts: Optional[float] = None


class OwnershipProjectionsPlayer(OwnershipPlayer):
    """OwnershipPlayer plus the *initial* ownership% -- used only by the
    Ownership Summary tab (backend/api/ownership/projections.py), which
    tracks both the very first ownership file ever uploaded for a
    (season, week, platform) and whatever's been uploaded most recently
    (ownership is typically first available Friday, then refreshed
    Saturday -- see backend/repositories/ownership/projections_repo.py's
    docstring). The inherited `ownership_pct` field keeps meaning exactly
    what it means everywhere else in this app -- the current/latest
    value -- so this is purely additive, not a redefinition.
    initial_ownership_pct is None for a player who wasn't in the initial
    upload at all (added in a later re-upload)."""

    initial_ownership_pct: Optional[float] = None


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


class PositionBlock(BaseModel):
    """One same-position combination of `block_size` players (e.g. all
    3-RB groups) plus their combined salary -- see
    backend/services/ownership/position_blocks.py's compute_position_blocks().
    `players` is sorted by salary descending within the block; the list of
    blocks itself is sorted by total_salary descending.

    total_expected_fpts is just the sum of each player's own
    OwnershipPlayer.expected_fpts (0.0 for any player missing one, though
    in practice every player in a block has the same platform's multiplier
    resolved, so either all of them have a real value or none do)."""

    players: list[OwnershipPlayer]
    total_salary: int
    total_expected_fpts: float = 0.0


class GameBlock(BaseModel):
    """One "game block" -- an RB/WR/TE combination of players drawn from a
    single NFL game, with both teams represented at least once -- see
    backend/services/ownership/game_blocks.py's compute_game_blocks().
    Unlike PositionBlock, players can mix positions and teams freely
    within those constraints. Backs Salary Blocks' Onslaught section;
    total block size defaults to 2-5 but Onslaught's own UI requests up to
    2-7 (see game_blocks.py's max_size).

    primary_team/primary_count describe whichever side of the matchup has
    *more* players in this block; bringback_team/bringback_count the
    other side -- filterable independently via Onslaught's "team"/"bring
    back team" size filters (see game_blocks.py's filter_by_primary_size/
    filter_by_bringback_size).

    `players` is sorted by salary descending within the block; the list of
    blocks itself is sorted by total_salary descending, same convention as
    PositionBlock."""

    players: list[OwnershipPlayer]
    total_salary: int
    total_expected_fpts: float = 0.0
    primary_team: str
    primary_count: int
    bringback_team: str
    bringback_count: int


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
