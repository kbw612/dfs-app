"""
Combines every Current Week endpoint (get.py, set.py) into one router
under the "/current-week" prefix. main.py mounts this under "/api", giving
GET /api/current-week and PUT /api/current-week.
"""

from fastapi import APIRouter

from backend.api.current_week.get import router as get_router
from backend.api.current_week.set import router as set_router

router = APIRouter()
router.include_router(get_router)
router.include_router(set_router)
