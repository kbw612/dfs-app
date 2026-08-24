"""
GET /snapshots?season=&week= (mounted at /api/ownership/snapshots -- see
backend/api/ownership/__init__.py). Lists every saved ownership snapshot,
newest first, optionally narrowed to one (season, week) -- lets the
frontend enumerate what's on disk for the diff picker, same role as
depth_charts/snapshots.py.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.snapshot_repo import list_snapshots, load_snapshot, snapshot_id_from_path

router = APIRouter()


class OwnershipSnapshotSummary(BaseModel):
    id: str
    scraped_at: str
    season: int
    week: int
    player_count: int


@router.get("/snapshots", response_model=list[OwnershipSnapshotSummary])
def list_ownership_snapshots_endpoint(
    season: Optional[int] = None, week: Optional[int] = None
) -> list[OwnershipSnapshotSummary]:
    summaries = []
    for path in list_snapshots(settings.ownership_snapshots_dir, season=season, week=week):
        snapshot = load_snapshot(path)
        summaries.append(
            OwnershipSnapshotSummary(
                id=snapshot_id_from_path(path),
                scraped_at=snapshot.scraped_at,
                season=snapshot.season,
                week=snapshot.week,
                player_count=len(snapshot.players),
            )
        )
    summaries.reverse()  # newest first
    return summaries
