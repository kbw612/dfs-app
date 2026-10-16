"""
GET /links?season=&week= (mounted at /api/game-recap/links -- see
backend/api/game_recap/__init__.py). Backs the Settings Game Recaps panel's
"browse the recap site" link: returns the one WalterFootball URL that
actually has this (season, week)'s recaps, or None when neither does.

WalterFootball only numbers a week's page (nflreview{season}_{week:02d}.php)
once that week is archived; until then the recaps live only on the bare
current-week page (nflreview.php). So a link built blindly from the numbered
template 404s for the latest week. This checks the numbered page first, then
falls back to the bare page if its own <title> names the requested week --
the same order and validation scrape() uses in "auto" mode.
"""

from __future__ import annotations

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.services.game_recap.game_recap_scraper import _page_matches_week, build_recap_url, fetch_html

router = APIRouter()


class GameRecapLinks(BaseModel):
    # The page that has this week's recaps, or None if neither the numbered
    # nor the current-week page does (week not published yet, or the site
    # couldn't be reached).
    url: str | None
    # "week_page" (archived numbered page) or "current_page" (bare page).
    kind: str | None
    # Always the bare current-week page, for a general "browse the site" link.
    current_url: str


@router.get("/links", response_model=GameRecapLinks)
def game_recap_links_endpoint(season: int, week: int) -> GameRecapLinks:
    current_url = settings.walterfootball_recap_current_url
    numbered_url = build_recap_url(season, week)
    try:
        response = fetch_html(numbered_url)
        if response.status_code == 200:
            return GameRecapLinks(url=numbered_url, kind="week_page", current_url=current_url)
        current = fetch_html(current_url)
        if current.status_code == 200 and _page_matches_week(current.text, season, week):
            return GameRecapLinks(url=current_url, kind="current_page", current_url=current_url)
    except requests.RequestException:
        pass
    return GameRecapLinks(url=None, kind=None, current_url=current_url)
