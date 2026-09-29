"""
Combines every Star Players endpoint (latest.py, entry.py) into one
router under the "/star-players" prefix. main.py mounts this under
"/api", giving GET /api/star-players/latest and PUT
/api/star-players/entry -- same aggregation pattern as
backend/api/team_factors/__init__.py.
"""

from fastapi import APIRouter

from backend.api.star_players.entry import router as entry_router
from backend.api.star_players.latest import router as latest_router

router = APIRouter(prefix="/star-players")
router.include_router(latest_router)
router.include_router(entry_router)
