"""
Combines every ownership endpoint (scrape.py, import_csv.py, latest.py,
diff.py, snapshots.py, position_blocks.py, game_blocks.py,
upload_projections_csv.py, projections_file.py, projections_file_info.py,
projections.py) into one router under the "/ownership" prefix. main.py
mounts this under "/api", giving POST /api/ownership/scrape, POST
/api/ownership/import-csv, GET /api/ownership/latest, GET
/api/ownership/diff/latest, GET /api/ownership/diff, GET
/api/ownership/snapshots, GET /api/ownership/position-blocks, GET
/api/ownership/game-blocks, POST /api/ownership/upload-projections-csv,
POST /api/ownership/scrape-main-slate, GET
/api/ownership/projections-file, GET
/api/ownership/projections-file-info, and GET /api/ownership/projections.

scrape-main-slate (see scrape_main_slate.py) is a second way to *produce*
the same projections CSV upload-projections-csv saves -- a login-free
scrape of oneweekseason.com's DraftKings Main Slate page, offered
alongside (not instead of) the manual upload as a backup.

game_blocks.py backs Salary Blocks' Onslaught section -- a different
combination shape (multi-position, both-teams-in-a-game) than
position_blocks.py's single-position blocks, but the same tab and the same
DK-salary-plus-enrichment data source; see its own docstring.

import-csv is a temporary stand-in for scrape while live scraping isn't
wired up yet -- see import_csv.py's docstring. Both save through the same
snapshot_repo, so everything downstream of "a snapshot exists on disk"
works identically either way.

upload-projections-csv/projections-file/projections-file-info/projections
are a separate, newer path (the Settings tab's single-file ownership
upload -- see upload_projections_csv.py's docstring). Player Pool and
Salary Blocks still read the older scrape/import-csv-driven
OwnershipSnapshot for their own ownership_pct enrichment (see
backend/services/player_pool/enrichment.py) -- integrating those onto this
newer upload is still future work. latest.py (Ownership Pivots) and
projections.py (Ownership Summary) both read this newer upload instead --
see their own docstrings for why each tab wants this file's player list
rather than the older snapshot's.
"""

from fastapi import APIRouter

from backend.api.ownership.diff import router as diff_router
from backend.api.ownership.game_blocks import router as game_blocks_router
from backend.api.ownership.import_csv import router as import_csv_router
from backend.api.ownership.latest import router as latest_router
from backend.api.ownership.position_blocks import router as position_blocks_router
from backend.api.ownership.projections import router as projections_router
from backend.api.ownership.projections_file import router as projections_file_router
from backend.api.ownership.projections_file_info import router as projections_file_info_router
from backend.api.ownership.scrape import router as scrape_router
from backend.api.ownership.scrape_main_slate import router as scrape_main_slate_router
from backend.api.ownership.snapshots import router as snapshots_router
from backend.api.ownership.upload_projections_csv import router as upload_projections_csv_router

router = APIRouter(prefix="/ownership")
router.include_router(scrape_router)
router.include_router(import_csv_router)
router.include_router(latest_router)
router.include_router(diff_router)
router.include_router(snapshots_router)
router.include_router(position_blocks_router)
router.include_router(game_blocks_router)
router.include_router(upload_projections_csv_router)
router.include_router(scrape_main_slate_router)
router.include_router(projections_file_router)
router.include_router(projections_file_info_router)
router.include_router(projections_router)
