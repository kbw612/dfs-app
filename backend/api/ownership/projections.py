"""
GET /projections?season=&week=&platform= (mounted at
/api/ownership/projections -- see backend/api/ownership/__init__.py).
Parses the raw CSVs saved by POST /upload-projections-csv (see
projections_repo.py's docstring for the initial-vs-current file pair) into
structured OwnershipProjectionsPlayer rows, merged together -- unlike GET
/projections-file (returns the raw current CSV text, for viewing/
downloading) or GET /projections-file-info (just filenames/timestamps),
this is the read path for anything that wants the *players themselves*,
e.g. the Ownership Summary tab.

Since the current file only ever contains the specific players someone
chose to include when exporting their projections for the week, `players`
here is exactly "whoever has a projected ownership% in the *current*
upload" -- a subset of the full DK salary slate, not the same universe
Player Pool/Salary Blocks use (those read the DK salary file plus the
older mock-scrape/live-scrape OwnershipSnapshot, an entirely separate data
source -- see backend/services/dk_salary/ownership_enrich.py). A player
who was in an earlier upload but dropped from the current one simply
doesn't appear at all, by design -- this endpoint always reflects "the
players in the latest file," never a union across uploads.

Each returned player's `initial_ownership_pct` comes from matching that
same player name against the *initial* upload (the very first ever saved
for this season/week/platform, see projections_repo.py) -- None if this
player wasn't in that initial file (e.g. added in a later re-upload).
When there's no separate initial file at all (an upload made before this
initial/current tracking existed, or the initial file failed to save for
some reason), the current file's own text is used as its own initial --
so a lone upload always shows initial == current, matching this feature's
"first upload, both match" design exactly, rather than showing every
player's initial as blank.

`platform` defaults to "DraftKings", same convention as every other
platform-scoped endpoint. 404 if nothing's been uploaded yet for this
(season, week, platform).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.ownership.projections_repo import (
    initial_projections_csv_path,
    load_initial_projections_csv,
    load_projections_csv,
    projections_csv_path,
)
from backend.schemas.ownership.ownership import OwnershipProjectionsPlayer
from backend.services.ownership.csv_loader import parse_ownership_projections_csv

router = APIRouter()


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


class OwnershipProjectionsResult(BaseModel):
    season: int
    week: int
    # On-disk modified time of the initial/current files respectively --
    # same convention as GET /projections-file-info. Equal for a
    # (season, week, platform) that's only ever been uploaded once.
    initial_uploaded_at: str
    current_uploaded_at: str
    players: list[OwnershipProjectionsPlayer]


@router.get("/projections", response_model=OwnershipProjectionsResult)
def ownership_projections_endpoint(season: int, week: int, platform: str = "DraftKings") -> OwnershipProjectionsResult:
    try:
        current_path = projections_csv_path(settings.nfl_data_dir, season, week, platform)
        current_csv_text = load_projections_csv(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if current_csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No ownership projections file uploaded yet for season {season} week {week} -- "
                "upload it in the Settings tab."
            ),
        )
    current_players, _messages = parse_ownership_projections_csv(current_csv_text)

    initial_path = initial_projections_csv_path(settings.nfl_data_dir, season, week, platform)
    # Fall back to the current file's own text when there's no separate
    # initial file -- see this module's docstring for why (keeps a lone
    # upload's initial == current instead of every player showing a
    # blank initial_ownership_pct).
    initial_csv_text = load_initial_projections_csv(settings.nfl_data_dir, season, week, platform) or current_csv_text
    initial_players, _messages = parse_ownership_projections_csv(initial_csv_text)
    initial_ownership_by_name = {p.player: p.ownership_pct for p in initial_players}

    players = [
        OwnershipProjectionsPlayer(
            **current_player.model_dump(),
            initial_ownership_pct=initial_ownership_by_name.get(current_player.player),
        )
        for current_player in current_players
    ]

    return OwnershipProjectionsResult(
        season=season,
        week=week,
        initial_uploaded_at=_mtime_iso(initial_path) if initial_path.exists() else _mtime_iso(current_path),
        current_uploaded_at=_mtime_iso(current_path),
        players=players,
    )
