"""
Combines every Player Pool endpoint (latest.py, entry.py) into one router
under the "/player-pool" prefix. main.py mounts this under "/api", giving
GET /api/player-pool/latest and PUT /api/player-pool/entry.

Game Environment inputs (odds/implied totals) and the DK salary upload
both live under their own top-level endpoints instead
(/api/game-environment/*, /api/dk-salary/* -- see
backend/api/game_environment/__init__.py and backend/api/dk_salary/
__init__.py) -- that data is shared across tabs, not owned by Player Pool,
even though this is currently the only tab that reads/displays Game
Environment (see backend/services/player_pool/engine.py).
"""

from fastapi import APIRouter

from backend.api.player_pool.entry import router as entry_router
from backend.api.player_pool.latest import router as latest_router

router = APIRouter(prefix="/player-pool")
router.include_router(latest_router)
router.include_router(entry_router)
