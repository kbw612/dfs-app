"""GET /api/player-signals -- see player_signals.py."""

from fastapi import APIRouter

from backend.api.player_signals.player_signals import router as player_signals_router

router = APIRouter()
router.include_router(player_signals_router)
