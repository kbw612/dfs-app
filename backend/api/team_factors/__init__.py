"""
Combines every Team Default Factors endpoint (latest.py, entry.py) into
one router under the "/team-factors" prefix. main.py mounts this under
"/api", giving GET /api/team-factors/latest and PUT
/api/team-factors/entry -- same aggregation pattern as
backend/api/player_defaults/__init__.py.
"""

from fastapi import APIRouter

from backend.api.team_factors.entry import router as entry_router
from backend.api.team_factors.latest import router as latest_router

router = APIRouter(prefix="/team-factors")
router.include_router(latest_router)
router.include_router(entry_router)
