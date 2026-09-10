"""
Combines every My Player Pool endpoint (latest.py, entry.py) into one
router under the "/my-player-pool" prefix. main.py mounts this under
"/api", giving GET /api/my-player-pool/latest and
PUT /api/my-player-pool/entry.
"""

from fastapi import APIRouter

from backend.api.my_player_pool.entry import router as entry_router
from backend.api.my_player_pool.latest import router as latest_router

router = APIRouter(prefix="/my-player-pool")
router.include_router(latest_router)
router.include_router(entry_router)
