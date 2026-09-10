"""
A flat, offense-only view of the latest depth-chart snapshot -- one row
per (team, position, depth_rank) for QB/RB/WR/TE, independent of any
week's DK salary file, platform, or contest (see
backend/services/depth_charts/roster.py). Built for Settings' Player
Default Factors grid (see backend/api/depth_charts/roster.py's
docstring), which needs every depth-chart-eligible player across all 32
teams regardless of which teams happen to be on a given week's slate.
"""

from __future__ import annotations

from pydantic import BaseModel


class RosterPlayer(BaseModel):
    player: str
    position: str
    team: str
    depth_rank: int


class RosterResult(BaseModel):
    players: list[RosterPlayer]
