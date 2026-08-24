"""
POST /scrape?season=&week= (mounted at /api/ownership/scrape -- see
backend/api/ownership/__init__.py). Logs into oneweekseason.com, scrapes
that (season, week)'s DK ownership table, and saves it as a new snapshot
-- see backend/services/ownership/scraper.py. Returns a summary, not the
full player list (that's what GET /latest is for).

season/week are required query params rather than being inferred, per the
app's current manual-entry approach to slate selection (same spirit as
depth_charts -- Phase 1 is manual triggering only, no scheduler yet).
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.snapshot_repo import save_snapshot
from backend.schemas.depth_charts.snapshot import Message
from backend.services.ownership.scraper import scrape as run_scrape

router = APIRouter()


class OwnershipScrapeResult(BaseModel):
    snapshot_path: str
    scraped_at: str
    season: int
    week: int
    player_count: int
    message_counts: dict[str, int]
    messages: list[Message]


@router.post("/scrape", response_model=OwnershipScrapeResult)
def scrape_endpoint(season: int, week: int) -> OwnershipScrapeResult:
    try:
        snapshot, messages = run_scrape(season, week)
    except ValueError as e:
        # Missing credentials -- see settings.ownership_source_username/password.
        raise HTTPException(status_code=500, detail=str(e)) from e

    file_path = save_snapshot(snapshot, settings.ownership_snapshots_dir)

    return OwnershipScrapeResult(
        snapshot_path=str(file_path),
        scraped_at=snapshot.scraped_at,
        season=snapshot.season,
        week=snapshot.week,
        player_count=len(snapshot.players),
        message_counts=dict(Counter(m.level for m in messages)),
        messages=messages,
    )
