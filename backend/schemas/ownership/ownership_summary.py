"""
Backend-computed team/game ownership rollups for the Ownership Summary
tab -- see backend/services/ownership/ownership_summary.py's own module
docstring for why this moved server-side (a single source of truth shared
with Game Preview's own team_projected_ownership_pct(), both of which now
call backend/services/ownership/ownership_totals.py's sum_current_ownership_pct
for the "current" figure).

Mirrors the frontend's former computeTeamOwnership/computeGameOwnership
(OwnershipSummaryView.tsx) field-for-field, just renamed from that
function's own camelCase local variable names to this app's snake_case
schema convention: initial -> initial_total_ownership_pct, current ->
total_ownership_pct (kept as `total_ownership_pct`, not `current_...`, to
match TeamOwnership.totalOwnership's own naming exactly), actual ->
actual_total_ownership_pct.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.schemas.ownership.ownership import OwnershipProjectionsPlayer


class TeamOwnershipRollup(BaseModel):
    team: str
    initial_total_ownership_pct: float
    total_ownership_pct: float
    # None when no Contest Standings are uploaded yet for this (season,
    # week, platform, contest) -- distinct from a real 0% total, same
    # "unknown vs. genuinely zero" convention as everywhere else in this
    # app that surfaces Contest Standings-derived data.
    actual_total_ownership_pct: float | None = None


class GameOwnershipRollup(BaseModel):
    key: str
    label: str
    # None when this team's real home/away couldn't be resolved (no DK
    # salary file uploaded yet for this contest) -- see
    # ownership_summary.py's own docstring.
    away_team: str | None = None
    home_team: str | None = None
    initial_total_ownership_pct: float
    total_ownership_pct: float
    actual_total_ownership_pct: float | None = None
    # Every player in the game (any position, including DST), sorted by
    # ownership_pct descending -- backs the tab's own per-game detail
    # expand. Distinct from the totals above, which exclude DST.
    players: list[OwnershipProjectionsPlayer] = Field(default_factory=list)


class OwnershipSummaryResult(BaseModel):
    teams: list[TeamOwnershipRollup] = Field(default_factory=list)
    games: list[GameOwnershipRollup] = Field(default_factory=list)
