"""
Combines every depth-chart endpoint (scrape.py, diff.py, snapshots.py)
into one router under the "/depth-charts" prefix. main.py mounts this
under "/api", giving POST /api/depth-charts/scrape,
GET /api/depth-charts/diff/latest, GET /api/depth-charts/diff, and
GET /api/depth-charts/snapshots.

When another resource type gets its own scrape/diff services (e.g.
injuries), it gets the same shape: backend/api/injuries/__init__.py combining
its own scrape.py/diff.py under prefix="/injuries", mounted in main.py the
same way -- this file doesn't change when that happens.
"""

from fastapi import APIRouter

from backend.api.depth_charts.diff import router as diff_router
from backend.api.depth_charts.scrape import router as scrape_router
from backend.api.depth_charts.snapshots import router as snapshots_router

router = APIRouter(prefix="/depth-charts")
router.include_router(scrape_router)
router.include_router(diff_router)
router.include_router(snapshots_router)
