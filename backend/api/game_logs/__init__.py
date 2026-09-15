"""
Just one endpoint (game_logs.py's GET /game-logs) but still its own
top-level router/prefix, same convention as every other resource in this
app -- main.py mounts this under "/api", giving GET /api/game-logs.
"""

from fastapi import APIRouter

from backend.api.game_logs.game_logs import router as game_logs_router

router = APIRouter()
router.include_router(game_logs_router)
