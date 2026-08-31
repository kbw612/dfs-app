"""
Combines every DK Salary endpoint (import_csv.py, file.py, file_info.py)
into one router under the "/dk-salary" prefix. main.py mounts this under
"/api", giving POST /api/dk-salary/import-csv, GET /api/dk-salary/file,
and GET /api/dk-salary/file-info. Shared by Salary Blocks and Player Pool
-- not owned by either tab specifically, same reasoning as Game
Environment (see backend/api/game_environment/__init__.py).
"""

from fastapi import APIRouter

from backend.api.dk_salary.file import router as file_router
from backend.api.dk_salary.file_info import router as file_info_router
from backend.api.dk_salary.import_csv import router as import_csv_router

router = APIRouter(prefix="/dk-salary")
router.include_router(import_csv_router)
router.include_router(file_router)
router.include_router(file_info_router)
