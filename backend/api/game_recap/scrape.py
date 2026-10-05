"""
POST /scrape?season=&week=&url_mode= (mounted at /api/game-recap/scrape --
see backend/api/game_recap/__init__.py). Scrapes walterfootball.com's
public recap page (backend/services/game_recap/game_recap_scraper.py) and
fully replaces whatever was already saved for that (season, week) -- no
merge step needed (see GameRecapWeekSnapshot's own docstring for why
there's no initial/current split the way Vegas Lines has).

`url_mode` ("auto" | "week_page" | "current_page", default "auto") passes
straight through to game_recap_scraper.scrape() -- see that function's own
docstring for what each one does. Default "auto" preserves the original
numbered-then-bare fallback for any caller that doesn't care; the
Settings panel's own radio buttons (see GameRecapUpload.tsx) are what let
the person override it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.game_recap.game_recap_repo import save_game_recaps
from backend.schemas.game_recap.game_recap import GameRecapEntry, GameRecapWeekSnapshot
from backend.services.game_recap.game_recap_scraper import UrlMode
from backend.services.game_recap.game_recap_scraper import scrape as run_scrape

router = APIRouter()


class GameRecapScrapeResult(BaseModel):
    snapshot: GameRecapWeekSnapshot
    messages: list[str]


@router.post("/scrape", response_model=GameRecapScrapeResult)
def game_recap_scrape_endpoint(season: int, week: int, url_mode: UrlMode = "auto") -> GameRecapScrapeResult:
    try:
        scraped_games, messages, source_url = run_scrape(season, week, url_mode)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    scraped_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    snapshot = GameRecapWeekSnapshot(
        season=season,
        week=week,
        scraped_at=scraped_at,
        source_url=source_url,
        games=[
            GameRecapEntry(
                away_team=g.away_team,
                home_team=g.home_team,
                away_team_score=g.away_team_score,
                home_team_score=g.home_team_score,
                recap_text=g.recap_text,
            )
            for g in scraped_games
        ],
    )
    save_game_recaps(settings.nfl_data_dir, snapshot)
    return GameRecapScrapeResult(snapshot=snapshot, messages=messages)
