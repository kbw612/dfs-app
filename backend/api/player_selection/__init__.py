"""
Combines every Player Selection endpoint (latest.py, entry.py) into one
router under the "/player-selection" prefix. main.py mounts this under
"/api", giving GET /api/player-selection/latest and
PUT /api/player-selection/entry.
"""

from fastapi import APIRouter

from backend.api.player_selection.entry import router as entry_router
from backend.api.player_selection.latest import router as latest_router

router = APIRouter(prefix="/player-selection")
router.include_router(latest_router)
router.include_router(entry_router)
