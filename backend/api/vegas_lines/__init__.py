"""
Combines every Vegas Lines endpoint (latest.py, scrape.py, apply.py) into
one router under the "/vegas-lines" prefix. main.py mounts this under
"/api", giving GET /api/vegas-lines/latest, POST /api/vegas-lines/scrape,
and POST /api/vegas-lines/apply.
"""

from fastapi import APIRouter

from backend.api.vegas_lines.apply import router as apply_router
from backend.api.vegas_lines.latest import router as latest_router
from backend.api.vegas_lines.scrape import router as scrape_router

router = APIRouter(prefix="/vegas-lines")
router.include_router(latest_router)
router.include_router(scrape_router)
router.include_router(apply_router)
