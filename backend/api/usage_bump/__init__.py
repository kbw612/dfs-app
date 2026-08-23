"""
Combines every usage-bump endpoint into one router under the
"/opportunities" prefix, mounted under "/api" in main.py -- same shape as
backend/api/depth_charts/__init__.py. This is a derived-analysis resource: it
reads the latest depth-chart snapshot (plus the curated overrides file)
but produces its own response shape, so it lives in its own subpackage
rather than inside depth_charts.

Note: the URL prefix stays "/opportunities" (a public API contract) even
though the package dir and everything under it is named usage_bump --
that's the internal/external naming split, not an inconsistency.
"""

from fastapi import APIRouter

from backend.api.usage_bump.latest import router as latest_router

router = APIRouter(prefix="/opportunities")
router.include_router(latest_router)
