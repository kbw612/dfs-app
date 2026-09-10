"""
Combines every Salary Multiplier endpoint (latest.py, entry.py) into one
router under the "/salary-multiplier" prefix. main.py mounts this under
"/api", giving GET /api/salary-multiplier/latest and
PUT /api/salary-multiplier/entry.
"""

from fastapi import APIRouter

from backend.api.salary_multiplier.entry import router as entry_router
from backend.api.salary_multiplier.latest import router as latest_router

router = APIRouter(prefix="/salary-multiplier")
router.include_router(latest_router)
router.include_router(entry_router)
