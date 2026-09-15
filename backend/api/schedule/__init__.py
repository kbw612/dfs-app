"""
Combines every Schedule endpoint (import_csv.py, file_info.py) into one
router under the "/schedule" prefix. main.py mounts this under "/api",
giving POST /api/schedule/import-csv and GET /api/schedule/file-info.
Feeds the Game Logs tab's Opponent/GameLoc columns and Game filter (see
backend/services/game_logs/game_logs_engine.py) -- not owned by that tab
specifically any more than the DK salary file is owned by one tab, so
this stays its own top-level resource.
"""

from fastapi import APIRouter

from backend.api.schedule.file_info import router as file_info_router
from backend.api.schedule.import_csv import router as import_csv_router

router = APIRouter(prefix="/schedule")
router.include_router(import_csv_router)
router.include_router(file_info_router)
