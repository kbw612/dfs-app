"""
Combines every Game Logs Summary endpoint into one router. main.py mounts
this under "/api", giving GET /api/game-logs-summary.
"""

from fastapi import APIRouter

from backend.api.game_logs_summary.game_logs_summary import router as game_logs_summary_router

router = APIRouter()
router.include_router(game_logs_summary_router)
