"""
Player Groups for the One Week Season "Blink" lineup tool: named groups of
players with a Pct, Min and Max, and optional anchor players. Groups are
ordered (the order is the export order). A group is not tied to a team or
game -- it can be any set of players. Players are identified by DraftKings ID.

`pct` is a percent (0-100, as Blink's screen shows it); the exported file
stores it as a fraction.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GroupPlayer(BaseModel):
    id: str
    name: str
    anchor: bool = False


class PlayerGroup(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    pct: float = Field(default=100.0, ge=0, le=100)
    min: int = Field(default=1, ge=0)
    max: int = Field(default=9, ge=0)
    players: list[GroupPlayer] = []


class SummaryPlayer(GroupPlayer):
    salary: int | None = None  # None when not in this week's salary file
    position: str | None = None


class GroupSummary(PlayerGroup):
    """A group plus what the preview shows, calculated by the backend."""

    players: list[SummaryPlayer] = []
    player_count: int = 0
    salary_total: int = 0
    missing_ids: list[str] = []  # players not in this week's salary file


class GroupsState(BaseModel):
    groups: list[GroupSummary]
    warnings: list[str] = []


class PoolPlayer(BaseModel):
    id: str
    name: str
    position: str
    team: str
    opponent: str
    salary: int
    game_key: str


class GameChip(BaseModel):
    key: str
    label: str
    teams: list[str]


class PoolResult(BaseModel):
    games: list[GameChip]
    players: list[PoolPlayer]  # filtered, salary high to low
    min_salaries: dict[str, int] = {}  # lowest salary per position in the contest
    my_pool_count: int = 0  # players in My Player Pool this week (any position)
