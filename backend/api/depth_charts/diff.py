"""
Diff endpoints (mounted at /api/depth-charts/... -- see
backend/api/depth_charts/__init__.py). Both compute generate_diff() live, on
demand -- nothing here is pre-computed or persisted. Snapshots are kept
forever and diffing is cheap, so there's no need for a separate
saved-vs-ad-hoc distinction; "the last two" and "any two you pick" both go
through the same code path.

  GET /diff/latest         diffs the two most recently saved snapshots
  GET /diff?from=X&to=Y    diffs any two snapshots by id (see
                            snapshot_repo.snapshot_id_from_path() for what
                            an id looks like, and GET /snapshots to list
                            them)

This file can keep growing with more diff-shaped endpoints later without
splitting into new files.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import (
    find_snapshot_by_id,
    list_snapshots,
    load_snapshot,
    snapshot_id_from_path,
)
from backend.schemas.depth_charts.change import Change
from backend.services.depth_charts.diff import generate_diff

router = APIRouter()


class DiffResult(BaseModel):
    from_snapshot: str
    to_snapshot: str
    change_count: int
    changes: list[Change]


def _diff_result(from_path: Path, to_path: Path) -> DiffResult:
    changes = generate_diff(load_snapshot(from_path), load_snapshot(to_path))
    return DiffResult(
        from_snapshot=snapshot_id_from_path(from_path),
        to_snapshot=snapshot_id_from_path(to_path),
        change_count=len(changes),
        changes=changes,
    )


@router.get("/diff/latest", response_model=DiffResult)
def diff_latest_endpoint() -> DiffResult:
    snapshots = list_snapshots(settings.snapshots_dir)
    if len(snapshots) < 2:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Need at least two snapshots to diff -- only {len(snapshots)} on disk. "
                "Run /scrape again."
            ),
        )
    return _diff_result(snapshots[-2], snapshots[-1])


@router.get("/diff", response_model=DiffResult)
def diff_compare_endpoint(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
) -> DiffResult:
    from_path = find_snapshot_by_id(settings.snapshots_dir, from_)
    if from_path is None:
        raise HTTPException(status_code=404, detail=f"No snapshot found with id '{from_}'.")

    to_path = find_snapshot_by_id(settings.snapshots_dir, to)
    if to_path is None:
        raise HTTPException(status_code=404, detail=f"No snapshot found with id '{to}'.")

    return _diff_result(from_path, to_path)
