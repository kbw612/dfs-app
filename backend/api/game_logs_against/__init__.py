"""
Just one endpoint (game_logs_against.py's GET /game-logs-against) but still
its own top-level router/prefix, same convention as every other resource
in this app -- main.py mounts this under "/api", giving
GET /api/game-logs-against.
"""

from fastapi import APIRouter

from backend.api.game_logs_against.game_logs_against import router as game_logs_against_router

router = APIRouter()
router.include_router(game_logs_against_router)
