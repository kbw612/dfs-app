"""
GET /api/current-week (see backend/api/current_week/__init__.py). Returns
whatever was last saved via
PUT /api/current-week, or a sensible default (the current calendar year,
week 1) the very first time this is called before anyone's ever set it --
the frontend always gets back something usable rather than having to
special-case "no current week yet".
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.current_week.current_week_repo import load_current_week
from backend.schemas.current_week.current_week import CurrentWeek

router = APIRouter()


@router.get("/current-week", response_model=CurrentWeek)
def current_week_get_endpoint() -> CurrentWeek:
    saved = load_current_week(settings.current_week_dir)
    if saved is not None:
        return saved
    return CurrentWeek(season=datetime.now(timezone.utc).year, week=1)
