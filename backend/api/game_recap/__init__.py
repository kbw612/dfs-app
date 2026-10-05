"""
Combines every Game Recap endpoint (latest.py, scrape.py) into one router
under the "/game-recap" prefix. main.py mounts this under "/api", giving
GET /api/game-recap/latest and POST /api/game-recap/scrape.
"""

from fastapi import APIRouter

from backend.api.game_recap.latest import router as latest_router
from backend.api.game_recap.scrape import router as scrape_router

router = APIRouter(prefix="/game-recap")
router.include_router(latest_router)
router.include_router(scrape_router)
