"""
PUT /api/platform-settings (see backend/api/platform_settings/__init__.py).
Body is a full PlatformSettings -- overwrites whatever was saved before.
Settings' Platform/Contest panel calls this whenever a chip is selected
(see frontend/src/components/SettingsView.tsx), so switching platforms in
one place is immediately what every other tab sees the next time it loads.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.platform_settings.platform_settings_repo import save_platform_settings
from backend.schemas.platform_settings.platform_settings import PlatformSettings

router = APIRouter()


@router.put("/platform-settings", response_model=PlatformSettings)
def platform_settings_set_endpoint(entry: PlatformSettings) -> PlatformSettings:
    save_platform_settings(settings.platform_settings_dir, entry)
    return entry
