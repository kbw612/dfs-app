"""
Results Tracker: a person's own contest entries and winnings, kept per season
(not per week -- a week is just a column in the grid). Stored as plain JSON.

A contest is a named entry type (e.g. "mini-Max (.50)"). An entry is one
contest played in one week: the total dollars spent, total dollars won, and
the best finishes. A week/contest with NO entry is a week not played -- it
counts toward nothing. ROI and totals are never stored; see
backend/services/contest_tracker/summary.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

MAX_WEEK = 22  # regular season plus playoffs


class TopFinish(BaseModel):
    place: int = Field(ge=1)
    payout: float = Field(ge=0)


class TrackerEntry(BaseModel):
    contest_id: str
    week: int = Field(ge=1, le=MAX_WEEK)
    cost: float = Field(gt=0)  # US dollars spent in this contest this week
    won: float = Field(ge=0)  # US dollars paid out
    top_finishes: list[TopFinish] = []


class TrackerContest(BaseModel):
    id: str
    name: str


class TrackerFile(BaseModel):
    """What is saved on disk."""

    season: int
    contests: list[TrackerContest] = []
    entries: list[TrackerEntry] = []


class ContestSummary(BaseModel):
    id: str
    name: str
    entries: list[TrackerEntry]
    cost: float
    won: float
    roi_pct: float | None  # None when nothing was played
    played: int


class ContestTrackerResult(BaseModel):
    season: int
    # Latest week with any entry; the "of N" in each contest's Played count.
    weeks_elapsed: int
    contests: list[ContestSummary]
    # Net dollars (won minus cost) across all contests for each week that has
    # at least one entry; weeks with none are absent.
    week_net: dict[int, float]
    total_cost: float
    total_won: float
    total_roi_pct: float | None
    net: float
