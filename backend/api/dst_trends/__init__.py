"""
Just one endpoint (dst_trends.py's GET /dst-trends) but still its own
top-level router/prefix, same convention as every other resource in this
app -- main.py mounts this under "/api", giving GET /api/dst-trends.
"""

from fastapi import APIRouter

from backend.api.dst_trends.dst_trends import router as dst_trends_router

router = APIRouter()
router.include_router(dst_trends_router)
