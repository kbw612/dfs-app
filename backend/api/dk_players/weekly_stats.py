"""
POST /weekly-stats/import-csv?season=&week=&position=,
POST /weekly-stats/scrape?season=&week=, and
GET /weekly-stats/file-info?season=&week= (mounted at
/api/dk-players/weekly-stats/...). The 4 per-position FantasyData stat
files (QB/RB/WR/TE) that feed calculate-week-points -- see
backend/repositories/dk_players/weekly_stats_repo.py for the season-long,
one-file-per-position storage model. Both import and scrape hand in one
week's rows and go through the exact same merge_week_into_season_csv path
(folded into that position's FantasyData_{QBs,RBs,WRs,TEs}.csv, replacing
just that week's rows) -- scrape is simply a second way to *produce* the
CSV text a manual upload would otherwise supply, no login required (see
backend/services/dk_players/weekly_stats_scraper.py). The manual-upload
button in Settings stays in place as a backup for whenever the scrape
can't run (site change, network issue, etc.). file-info reports all 4
positions' status at once so Settings can show a single combined panel,
and is also what the frontend calls before an import/scrape to decide
whether to show an overwrite-confirmation prompt (a position's season
file can already exist from an earlier week, so "already has this week's
data" has to be judged by week_has_data(), not by file existence).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import requests
from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_players.weekly_stats_repo import (
    Position,
    merge_week_into_season_csv,
    week_has_data,
    weekly_stats_csv_path,
)
from backend.schemas.dk_players.dk_players import WeeklyStatsImportResult
from backend.services.dk_players.weekly_stats_scraper import WeeklyStatsScrapeError, scrape_weekly_stats_csv

router = APIRouter()

_POSITIONS: list[Position] = ["QB", "RB", "WR", "TE"]


@router.post("/weekly-stats/import-csv", response_model=WeeklyStatsImportResult)
async def import_weekly_stats_csv_endpoint(
    season: int, week: int, position: Literal["QB", "RB", "WR", "TE"], file: UploadFile = File(...)
) -> WeeklyStatsImportResult:
    raw_bytes = await file.read()
    csv_text = raw_bytes.decode("utf-8-sig")
    merge_week_into_season_csv(settings.nfl_data_dir, season, position, week, csv_text)
    row_count = max(csv_text.strip().count("\n"), 0)  # header line doesn't count as a row
    return WeeklyStatsImportResult(season=season, week=week, position=position, row_count=row_count)


class WeeklyStatsFileStatus(BaseModel):
    position: str
    # The season file's own name (e.g. "FantasyData_QBs.csv") -- always
    # present once ANY week has ever been saved for this position, even if
    # `week` itself hasn't been.
    filename: str | None
    # On-disk mtime of the season file -- reflects the last time ANY
    # week's data was saved to it, not specifically `week`'s (there's no
    # per-week timestamp inside a shared season file). Still None if the
    # file doesn't exist at all yet.
    uploaded_at: str | None
    # Whether `week` specifically already has rows in the season file --
    # this, not `filename`/`uploaded_at`, is what the frontend should use
    # to decide whether importing/scraping would overwrite something.
    week_has_data: bool


class WeeklyStatsFileInfoResult(BaseModel):
    files: list[WeeklyStatsFileStatus]


@router.get("/weekly-stats/file-info", response_model=WeeklyStatsFileInfoResult)
def weekly_stats_file_info_endpoint(season: int, week: int) -> WeeklyStatsFileInfoResult:
    statuses = []
    for position in _POSITIONS:
        file_path = weekly_stats_csv_path(settings.nfl_data_dir, season, position)
        if file_path.exists():
            uploaded_at = datetime.fromtimestamp(file_path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
            statuses.append(
                WeeklyStatsFileStatus(
                    position=position,
                    filename=file_path.name,
                    uploaded_at=uploaded_at,
                    week_has_data=week_has_data(settings.nfl_data_dir, season, position, week),
                )
            )
        else:
            statuses.append(
                WeeklyStatsFileStatus(position=position, filename=None, uploaded_at=None, week_has_data=False)
            )
    return WeeklyStatsFileInfoResult(files=statuses)


class WeeklyStatsScrapePositionResult(BaseModel):
    position: str
    row_count: int | None
    error: str | None


class WeeklyStatsScrapeResult(BaseModel):
    season: int
    week: int
    results: list[WeeklyStatsScrapePositionResult]


@router.post("/weekly-stats/scrape", response_model=WeeklyStatsScrapeResult)
def scrape_weekly_stats_endpoint(season: int, week: int) -> WeeklyStatsScrapeResult:
    """Scrapes all 4 positions from FantasyData and merges each one that
    succeeds into that position's season file -- a failure on one
    position (network error, site markup changed, etc.) is recorded in
    that position's `error` field rather than aborting the other 3.
    Always overwrites `week`'s own rows if they already exist (leaving
    every other week's rows alone) -- the frontend is responsible for
    confirming that with the user first (via GET /weekly-stats/file-info's
    week_has_data) before calling this."""
    results: list[WeeklyStatsScrapePositionResult] = []
    for position in _POSITIONS:
        try:
            csv_text = scrape_weekly_stats_csv(season, week, position)
        except (WeeklyStatsScrapeError, requests.RequestException) as exc:
            results.append(WeeklyStatsScrapePositionResult(position=position, row_count=None, error=str(exc)))
            continue
        merge_week_into_season_csv(settings.nfl_data_dir, season, position, week, csv_text)
        row_count = max(csv_text.strip().count("\n"), 0)  # header line doesn't count as a row
        results.append(WeeklyStatsScrapePositionResult(position=position, row_count=row_count, error=None))
    return WeeklyStatsScrapeResult(season=season, week=week, results=results)
