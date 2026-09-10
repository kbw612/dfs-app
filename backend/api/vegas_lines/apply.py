"""
POST /apply?season=&week= (mounted at /api/vegas-lines/apply -- see
backend/api/vegas_lines/__init__.py). Takes whatever's already saved in
this week's Vegas Lines (backend/repositories/vegas_lines/
vegas_lines_repo.py -- does NOT scrape live itself) and writes each
resolved game's `current` values into that week's Game Environment
scores, wholesale-replacing them the same way backend/services/
game_environment/game_environment_repo.py's replace_week() always has
("latest applied wins," no per-game merge with whatever was there
before).

404s if nothing's been scraped yet for this (season, week) -- this
endpoint has nothing to apply in that case, and shouldn't silently no-op.
A game whose team name(s) never resolved to an abbreviation (see
scraper.py's docstring) is skipped, not guessed at -- `messages` reports
exactly which ones.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.game_environment.game_environment_repo import replace_week
from backend.repositories.vegas_lines.vegas_lines_repo import load_vegas_lines
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry

router = APIRouter()


class VegasLinesApplyResult(BaseModel):
    season: int
    week: int
    applied_count: int
    skipped_count: int
    messages: list[str]


@router.post("/apply", response_model=VegasLinesApplyResult)
def vegas_lines_apply_endpoint(season: int, week: int) -> VegasLinesApplyResult:
    snapshot = load_vegas_lines(settings.nfl_data_dir, season, week)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Vegas Lines scraped yet for season {season} week {week} -- "
                "retrieve them on the Vegas Lines tab first."
            ),
        )

    entries: list[GameEnvironmentEntry] = []
    messages: list[str] = []
    for game in snapshot.games:
        if game.game_key is None or game.home_team is None or game.away_team is None:
            messages.append(f"Skipped {game.away_name} at {game.home_name} -- team name(s) unresolved")
            continue
        entries.append(
            GameEnvironmentEntry(
                season=season,
                week=week,
                game_key=game.game_key,
                home_team=game.home_team,
                away_team=game.away_team,
                over_under=game.current.over_under,
                home_implied_total=game.current.home_implied_total,
                away_implied_total=game.current.away_implied_total,
            )
        )

    replace_week(settings.game_environment_dir, season, week, entries)

    return VegasLinesApplyResult(
        season=season, week=week, applied_count=len(entries), skipped_count=len(messages), messages=messages
    )
