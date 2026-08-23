"""
Entrypoint. Run locally with:

    uvicorn backend.main:app --reload

Then trigger a scrape manually:

    curl -X POST http://127.0.0.1:8000/api/depth-charts/scrape

...and see what changed since the last one:

    curl http://127.0.0.1:8000/api/depth-charts/diff/latest

The React frontend (frontend/) runs as its own dev server (Vite, default
port 5173) rather than being served by this app -- see frontend/README.md.
CORS is opened up for that origin below so the browser can call this API
directly during local development.

Every resource's endpoints (depth-charts today, more later -- injuries,
salaries, etc.) get mounted under "/api". /health stays unprefixed at the
root since it's an app-level endpoint, not part of the resource API.

Phase 1 (Section 2 of the design doc) is manual triggering only -- no
scheduler yet. Cloud Scheduler + OIDC verification get added in Phase 2.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.depth_charts import router as depth_charts_router
from backend.api.usage_bump import router as usage_bump_router
from backend.config import settings

app = FastAPI(title="dfs-app", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(depth_charts_router, prefix="/api")
app.include_router(usage_bump_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
