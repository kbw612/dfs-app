"""
Combines the Injury Report endpoint (latest.py) into one router under the
"/injury-report" prefix. main.py mounts this under "/api", giving
GET /api/injury-report/latest -- same aggregation pattern as
backend/api/star_players/__init__.py.
"""

from fastapi import APIRouter

from backend.api.injury_report.latest import router as latest_router

router = APIRouter(prefix="/injury-report")
router.include_router(latest_router)
