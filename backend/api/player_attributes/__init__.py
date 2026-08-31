"""
Combines every Player Attributes endpoint (latest.py, entry.py) into one
router under the "/player-attributes" prefix. main.py mounts this under
"/api", giving GET /api/player-attributes/latest and PUT
/api/player-attributes/entry.
"""

from fastapi import APIRouter

from backend.api.player_attributes.entry import router as entry_router
from backend.api.player_attributes.latest import router as latest_router

router = APIRouter(prefix="/player-attributes")
router.include_router(latest_router)
router.include_router(entry_router)
