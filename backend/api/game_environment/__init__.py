"""
Combines every Game Environment endpoint (latest.py, entry.py) into one
router under the "/game-environment" prefix. main.py mounts this under
"/api", giving GET /api/game-environment/latest and PUT
/api/game-environment/entry.
"""

from fastapi import APIRouter

from backend.api.game_environment.entry import router as entry_router
from backend.api.game_environment.latest import router as latest_router

router = APIRouter(prefix="/game-environment")
router.include_router(latest_router)
router.include_router(entry_router)
