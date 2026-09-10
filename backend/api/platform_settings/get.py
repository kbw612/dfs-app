"""
GET /platform-settings?season= (mounted at /api/platform-settings -- see
backend/api/platform_settings/__init__.py). Returns whatever was last
saved via PUT /api/platform-settings for that season, or a sensible
default ("DraftKings" / "Classic Main", the only platform and contest
actually supported today) the first time this is called for a season
before anyone's ever set it -- same "always usable, no special-casing an
empty state" pattern as GET /api/current-week.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.platform_settings.platform_settings_repo import load_platform_settings
from backend.schemas.platform_settings.platform_settings import PlatformSettings

router = APIRouter()


@router.get("/platform-settings", response_model=PlatformSettings)
def platform_settings_get_endpoint(season: int) -> PlatformSettings:
    saved = load_platform_settings(settings.nfl_data_dir, season)
    if saved is not None:
        return saved
    return PlatformSettings(season=season, platform="DraftKings", contest="Classic Main")
