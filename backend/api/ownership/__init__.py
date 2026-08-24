"""
Combines every ownership endpoint (scrape.py, import_csv.py, latest.py,
diff.py, snapshots.py) into one router under the "/ownership" prefix.
main.py mounts this under "/api", giving POST /api/ownership/scrape,
POST /api/ownership/import-csv, GET /api/ownership/latest,
GET /api/ownership/diff/latest, GET /api/ownership/diff, and
GET /api/ownership/snapshots.

import-csv is a temporary stand-in for scrape while live scraping isn't
wired up yet -- see import_csv.py's docstring. Both save through the same
snapshot_repo, so everything downstream of "a snapshot exists on disk"
works identically either way.
"""

from fastapi import APIRouter

from backend.api.ownership.diff import router as diff_router
from backend.api.ownership.import_csv import router as import_csv_router
from backend.api.ownership.latest import router as latest_router
from backend.api.ownership.scrape import router as scrape_router
from backend.api.ownership.snapshots import router as snapshots_router

router = APIRouter(prefix="/ownership")
router.include_router(scrape_router)
router.include_router(import_csv_router)
router.include_router(latest_router)
router.include_router(diff_router)
router.include_router(snapshots_router)
