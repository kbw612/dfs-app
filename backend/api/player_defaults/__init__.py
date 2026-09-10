"""
Combines every Player Defaults endpoint (latest.py, entry.py) into one
router under the "/player-defaults" prefix. main.py mounts this under
"/api", giving GET /api/player-defaults/latest and PUT
/api/player-defaults/entry.
"""

from fastapi import APIRouter

from backend.api.player_defaults.entry import router as entry_router
from backend.api.player_defaults.latest import router as latest_router

router = APIRouter(prefix="/player-defaults")
router.include_router(latest_router)
router.include_router(entry_router)
