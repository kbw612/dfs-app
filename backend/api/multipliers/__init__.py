"""
Just one endpoint (multipliers.py's GET /multipliers) but still its own
top-level router/prefix, same convention as every other resource in this
app -- main.py mounts this under "/api", giving GET /api/multipliers.
"""

from fastapi import APIRouter

from backend.api.multipliers.multipliers import router as multipliers_router

router = APIRouter()
router.include_router(multipliers_router)
