"""
Combines every ownership endpoint (scrape.py, import_csv.py, latest.py,
diff.py, snapshots.py, position_blocks.py, upload_projections_csv.py,
projections_file.py) into one router under the "/ownership" prefix.
main.py mounts this under "/api", giving POST /api/ownership/scrape, POST
/api/ownership/import-csv, GET /api/ownership/latest, GET
/api/ownership/diff/latest, GET /api/ownership/diff, GET
/api/ownership/snapshots, GET /api/ownership/position-blocks, POST
/api/ownership/upload-projections-csv, and GET
/api/ownership/projections-file.

import-csv is a temporary stand-in for scrape while live scraping isn't
wired up yet -- see import_csv.py's docstring. Both save through the same
snapshot_repo, so everything downstream of "a snapshot exists on disk"
works identically either way.

upload-projections-csv/projections-file are a separate, newer path (the
Settings tab's single-file ownership upload -- see
upload_projections_csv.py's docstring) that doesn't feed the
scrape/import-csv-driven analysis above; that integration is future work.
"""

from fastapi import APIRouter

from backend.api.ownership.diff import router as diff_router
from backend.api.ownership.import_csv import router as import_csv_router
from backend.api.ownership.latest import router as latest_router
from backend.api.ownership.position_blocks import router as position_blocks_router
from backend.api.ownership.projections_file import router as projections_file_router
from backend.api.ownership.projections_file_info import router as projections_file_info_router
from backend.api.ownership.scrape import router as scrape_router
from backend.api.ownership.snapshots import router as snapshots_router
from backend.api.ownership.upload_projections_csv import router as upload_projections_csv_router

router = APIRouter(prefix="/ownership")
router.include_router(scrape_router)
router.include_router(import_csv_router)
router.include_router(latest_router)
router.include_router(diff_router)
router.include_router(snapshots_router)
router.include_router(position_blocks_router)
router.include_router(upload_projections_csv_router)
router.include_router(projections_file_router)
router.include_router(projections_file_info_router)
