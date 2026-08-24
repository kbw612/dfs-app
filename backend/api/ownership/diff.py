"""
Diff endpoints (mounted at /api/ownership/... -- see
backend/api/ownership/__init__.py). Both compute compute_ownership_diff()
live, on demand -- same philosophy as depth_charts/diff.py.

  GET /diff/latest?season=&week=   diffs the two most recently saved
                                     snapshots *for that slate*
  GET /diff?from=X&to=Y             diffs any two snapshots by id (see
                                     snapshot_repo.snapshot_id_from_path())
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.snapshot_repo import (
    find_snapshot_by_id,
    list_snapshots,
    load_snapshot,
    snapshot_id_from_path,
)
from backend.schemas.ownership.ownership import OwnershipChange
from backend.services.ownership.engine import compute_ownership_diff

router = APIRouter()


class OwnershipDiffResult(BaseModel):
    from_snapshot: str
    to_snapshot: str
    change_count: int
    changes: list[OwnershipChange]


def _diff_result(from_path: Path, to_path: Path) -> OwnershipDiffResult:
    changes = compute_ownership_diff(load_snapshot(from_path), load_snapshot(to_path))
    return OwnershipDiffResult(
        from_snapshot=snapshot_id_from_path(from_path),
        to_snapshot=snapshot_id_from_path(to_path),
        change_count=len(changes),
        changes=changes,
    )


@router.get("/diff/latest", response_model=OwnershipDiffResult)
def ownership_diff_latest_endpoint(season: int, week: int) -> OwnershipDiffResult:
    snapshots = list_snapshots(settings.ownership_snapshots_dir, season=season, week=week)
    if len(snapshots) < 2:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Need at least two ownership snapshots for season {season} week {week} to diff -- "
                f"only {len(snapshots)} on disk. Run /scrape again."
            ),
        )
    return _diff_result(snapshots[-2], snapshots[-1])


@router.get("/diff", response_model=OwnershipDiffResult)
def ownership_diff_compare_endpoint(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
) -> OwnershipDiffResult:
    from_path = find_snapshot_by_id(settings.ownership_snapshots_dir, from_)
    if from_path is None:
        raise HTTPException(status_code=404, detail=f"No ownership snapshot found with id '{from_}'.")

    to_path = find_snapshot_by_id(settings.ownership_snapshots_dir, to)
    if to_path is None:
        raise HTTPException(status_code=404, detail=f"No ownership snapshot found with id '{to}'.")

    return _diff_result(from_path, to_path)
