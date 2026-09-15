"""
POST /scrape-main-slate?season=&week=&platform= (mounted at
/api/ownership/scrape-main-slate -- see backend/api/ownership/__init__.py).
Scrapes oneweekseason.com's public DraftKings Main Slate page (backend/
services/ownership/main_slate_scraper.py, no login required) and saves the
result through the exact same path as a manual upload
(backend/api/ownership/upload_projections_csv.py's save_projections_csv) --
this is a second way to *produce* the CSV that upload feeds, not a
separate storage location. The manual-upload button in Settings stays in
place as a backup for whenever the scrape can't run (site change, network
issue, etc.).

Refuses to save (409) if the live page's own "Week N" label doesn't match
the requested `week` -- guards against saving a different week's slate
under the wrong (season, week) key if the site has already rolled over to
a new week before the app's own week selector is switched. If the page's
week label can't be found at all, the scrape proceeds anyway (nothing to
cross-check against) but says so in the response messages.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.projections_repo import save_projections_csv
from backend.schemas.depth_charts.snapshot import Message
from backend.services.ownership.csv_loader import parse_ownership_projections_csv
from backend.services.ownership.main_slate_scraper import scrape_main_slate

router = APIRouter()


class OwnershipMainSlateScrapeResult(BaseModel):
    file_path: str
    season: int
    week: int
    player_count: int
    message_counts: dict[str, int]
    messages: list[Message]


@router.post("/scrape-main-slate", response_model=OwnershipMainSlateScrapeResult)
def scrape_main_slate_endpoint(season: int, week: int, platform: str = "DraftKings") -> OwnershipMainSlateScrapeResult:
    csv_text, displayed_week, scrape_messages = scrape_main_slate(settings.oneweekseason_main_slate_url)
    if csv_text is None:
        raise HTTPException(
            status_code=502, detail="; ".join(m.message for m in scrape_messages) or "Scrape failed"
        )

    messages = list(scrape_messages)
    if displayed_week is None:
        messages.append(
            Message(
                level="warning",
                step="scrape-main-slate",
                message="Couldn't determine which week the site is currently showing -- saved without that check",
            )
        )
    elif displayed_week != week:
        raise HTTPException(
            status_code=409,
            detail=(
                f"OneWeekSeason is currently showing Week {displayed_week}, "
                f"but Week {week} was requested -- not saved"
            ),
        )

    players, parse_messages = parse_ownership_projections_csv(csv_text)
    messages.extend(parse_messages)

    try:
        file_path = save_projections_csv(settings.nfl_data_dir, season, week, platform, csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return OwnershipMainSlateScrapeResult(
        file_path=str(file_path),
        season=season,
        week=week,
        player_count=len(players),
        message_counts=dict(Counter(m.level for m in messages)),
        messages=messages,
    )
