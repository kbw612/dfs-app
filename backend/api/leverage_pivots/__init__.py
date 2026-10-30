"""GET /api/leverage-pivots -- see leverage_pivots.py."""

from fastapi import APIRouter

from backend.api.leverage_pivots.leverage_pivots import router as leverage_pivots_router

router = APIRouter()
router.include_router(leverage_pivots_router)
