"""
GET /roster (mounted at /api/depth-charts/roster -- see
backend/api/depth_charts/__init__.py). The latest depth-chart snapshot,
flattened to one row per (team, position, depth_rank) for QB/RB/WR/TE
across all 32 teams -- independent of any week's DK salary file,
platform, or contest. Built for Settings' Player Default Factors grid
(see frontend/src/components/SettingsView.tsx), which sets a player's
Volume/Talent/DFS Type baseline once per season and needs every
depth-chart-eligible player to be settable regardless of which teams
happen to be on a given week's slate -- a team missing from that week's
salary export (bye week, a partial slate, an upload gap) shouldn't mean
its players are simply unreachable here.

Empty `players` (not a 404) if there's no depth-chart snapshot at all
yet -- same "not an error, just nothing scraped" treatment as everywhere
else a missing depth-chart snapshot is handled (e.g. ownership/latest.py's
depth-rank enrichment).
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.schemas.depth_charts.roster import RosterResult
from backend.services.depth_charts.roster import flatten_offense_roster

router = APIRouter()


@router.get("/roster", response_model=RosterResult)
def depth_chart_roster_endpoint() -> RosterResult:
    snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    snapshot = load_snapshot(snapshot_path) if snapshot_path else None
    return RosterResult(players=flatten_offense_roster(snapshot))
