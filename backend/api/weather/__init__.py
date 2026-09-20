"""
Combines every Weather endpoint (latest.py, scrape.py) into one router
under the "/weather" prefix. main.py mounts this under "/api", giving
GET /api/weather/latest and POST /api/weather/scrape.
"""

from fastapi import APIRouter

from backend.api.weather.latest import router as latest_router
from backend.api.weather.scrape import router as scrape_router

router = APIRouter(prefix="/weather")
router.include_router(latest_router)
router.include_router(scrape_router)
