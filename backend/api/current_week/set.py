"""
PUT /api/current-week (see backend/api/current_week/__init__.py). Body is
a full CurrentWeek --
overwrites whatever was saved before. Every tab that reads the shared
season/week control calls this on change (see frontend/src/App.tsx), so
switching weeks in one place is immediately what every other tab sees the
next time it loads.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.current_week.current_week_repo import save_current_week
from backend.schemas.current_week.current_week import CurrentWeek

router = APIRouter()


@router.put("/current-week", response_model=CurrentWeek)
def current_week_set_endpoint(entry: CurrentWeek) -> CurrentWeek:
    save_current_week(settings.current_week_dir, entry)
    return entry
