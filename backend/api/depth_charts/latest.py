"""
GET /latest (mounted at /api/depth-charts/latest -- see
backend/api/depth_charts/__init__.py). The full latest depth-chart
snapshot -- every team, every position, and each player's name and
status -- for the Depth Charts tab's by-team browse view.

Unlike roster.py's flatten_offense_roster (QB/RB/WR/TE only, no status --
built specifically for Settings' Player Default Factors grid), this
returns the Snapshot schema's own shape unmodified: every position
(offensive line, defensive line, linebackers, secondary, special teams)
and each player's injury status, since the Depth Charts tab's position
dropdown and status filter both need that full picture.

404s if nothing's been scraped yet -- same "retrieve it first" convention
as Vegas Lines/Weather's own latest endpoints. The Depth Charts tab has
its own Retrieve button (RetrieveButton.tsx, reused verbatim from Compare
Depth Charts), but it hits the same POST /api/depth-charts/scrape and
reads the exact same snapshot Compare Depth Charts does -- there's only
ever one depth-chart snapshot at a time, not a per-tab copy.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.schemas.depth_charts.snapshot import Snapshot

router = APIRouter()


@router.get("/latest", response_model=Snapshot)
def depth_charts_latest_endpoint() -> Snapshot:
    snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    if snapshot_path is None:
        raise HTTPException(
            status_code=404,
            detail="No depth chart scraped yet -- retrieve one first.",
        )
    return load_snapshot(snapshot_path)
