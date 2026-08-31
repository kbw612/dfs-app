"""
Combines every Platform Settings endpoint (get.py, set.py) into one router
under the "/platform-settings" prefix. main.py mounts this under "/api",
giving GET /api/platform-settings and PUT /api/platform-settings.
"""

from fastapi import APIRouter

from backend.api.platform_settings.get import router as get_router
from backend.api.platform_settings.set import router as set_router

router = APIRouter()
router.include_router(get_router)
router.include_router(set_router)
