"""
POST /scrape (mounted at /api/depth-charts/scrape -- see
backend/api/depth_charts/__init__.py) -- the one scrape endpoint in this
slice. Runs the pipeline and returns a summary, not the whole snapshot
(the snapshot itself is on disk; this response is just enough to confirm
the run and see counts at a glance).

    scrape() -> enrich_team_abbrev() -> enrich_defensive_formation()
      -> save_snapshot()

Diffing is deliberately NOT done here anymore -- it used to run
immediately after every scrape and persist a changes_{timestamp}.jsonl
file, but since every snapshot is kept forever and generate_diff() is
cheap, diffs are now always computed live, on demand, by
backend/api/depth_charts/diff.py (both "the last two snapshots" and "any two
arbitrary snapshots" go through the same live-computation path -- there's
no separate pre-computed-vs-ad-hoc distinction anymore).
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import save_snapshot
from backend.schemas.depth_charts.snapshot import Message
from backend.services.depth_charts.enrich import enrich_defensive_formation, enrich_team_abbrev
from backend.services.depth_charts.scraper import scrape as run_scrape

router = APIRouter()


class ScrapeResult(BaseModel):
    snapshot_path: str
    scraped_at: str
    team_count: int
    message_counts: dict[str, int]
    messages: list[Message]


@router.post("/scrape", response_model=ScrapeResult)
def scrape_endpoint() -> ScrapeResult:
    snapshot = run_scrape()
    snapshot = enrich_team_abbrev(snapshot, settings.team_info_csv)
    snapshot = enrich_defensive_formation(snapshot)

    file_path = save_snapshot(snapshot, settings.snapshots_dir)

    return ScrapeResult(
        snapshot_path=str(file_path),
        scraped_at=snapshot.scraped_at,
        team_count=len(snapshot.teams),
        message_counts=dict(Counter(m.level for m in snapshot.messages)),
        messages=snapshot.messages,
    )
