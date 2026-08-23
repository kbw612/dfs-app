"""
GET /snapshots (mounted at /api/depth-charts/snapshots -- see
backend/api/depth_charts/__init__.py) -- lists every saved snapshot, newest
first. This is what the frontend's picker uses to let you choose two
depth charts to compare (or just see what's available before hitting
POST /scrape to generate a new one).
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import (
    list_snapshots,
    load_snapshot,
    snapshot_id_from_path,
)

router = APIRouter()


class SnapshotSummary(BaseModel):
    id: str
    scraped_at: str
    team_count: int


@router.get("/snapshots", response_model=list[SnapshotSummary])
def list_snapshots_endpoint() -> list[SnapshotSummary]:
    summaries = []
    for path in list_snapshots(settings.snapshots_dir):
        snapshot = load_snapshot(path)
        summaries.append(
            SnapshotSummary(
                id=snapshot_id_from_path(path),
                scraped_at=snapshot.scraped_at,
                team_count=len(snapshot.teams),
            )
        )
    summaries.reverse()  # newest first
    return summaries
