"""
Combines every Lineup Scenarios endpoint (upload_csv.py, evaluate.py)
into one router under the "/lineup-scenarios" prefix. main.py mounts
this under "/api", giving POST /api/lineup-scenarios/upload and POST
/api/lineup-scenarios/evaluate.

Backs the standalone Lineup Scenarios tab -- a person uploads a batch of
lineups they already built in an external optimizer, defines one or more
team-stack "scenarios" they believe will play out, and this reports which
lineups actually roster enough players from each scenario's flagged
teams. See backend/services/lineup_scenarios/lineup_scenario_engine.py's
docstring for the exact satisfaction rule.
"""

from fastapi import APIRouter

from backend.api.lineup_scenarios.evaluate import router as evaluate_router
from backend.api.lineup_scenarios.upload_csv import router as upload_csv_router

router = APIRouter(prefix="/lineup-scenarios")
router.include_router(upload_csv_router)
router.include_router(evaluate_router)
