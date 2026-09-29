"""
Just one endpoint (game_preview.py's GET /game-preview) but still its own
top-level router/prefix, same convention as every other resource in this
app -- main.py mounts this under "/api", giving GET /api/game-preview.
"""

from fastapi import APIRouter

from backend.api.game_preview.game_preview import router as game_preview_router

router = APIRouter()
router.include_router(game_preview_router)
