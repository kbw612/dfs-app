"""
POST /import-csv?season=&week= (mounted at /api/ownership/import-csv --
see backend/api/ownership/__init__.py). Temporary stand-in for POST
/scrape while live scraping isn't wired up yet -- reads
backend/services/ownership/csv_loader.py's mock CSVs instead of logging
into oneweekseason.com, but saves the resulting snapshot through the same
snapshot_repo, so GET /latest and /diff work identically regardless of
which endpoint produced the snapshot on disk.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.snapshot_repo import save_snapshot
from backend.schemas.depth_charts.snapshot import Message
from backend.services.ownership.csv_loader import load_ownership_csv

router = APIRouter()


class OwnershipImportResult(BaseModel):
    snapshot_path: str
    scraped_at: str
    season: int
    week: int
    player_count: int
    message_counts: dict[str, int]
    messages: list[Message]


@router.post("/import-csv", response_model=OwnershipImportResult)
def import_csv_endpoint(season: int, week: int) -> OwnershipImportResult:
    snapshot, messages = load_ownership_csv(season, week, settings.ownership_mock_dir)
    file_path = save_snapshot(snapshot, settings.ownership_snapshots_dir)

    return OwnershipImportResult(
        snapshot_path=str(file_path),
        scraped_at=snapshot.scraped_at,
        season=snapshot.season,
        week=snapshot.week,
        player_count=len(snapshot.players),
        message_counts=dict(Counter(m.level for m in messages)),
        messages=messages,
    )
