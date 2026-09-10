"""
Combines every Contest Results endpoint (import_csv.py, top_lineups.py,
player_results.py) into one router under the "/contest-results" prefix.
main.py mounts this under "/api", giving POST
/api/contest-results/import-csv, GET /api/contest-results/top-lineups,
GET /api/contest-results/player-results, and GET
/api/contest-results/file-info.

Backs the standalone Contest Results tab -- parses a DraftKings contest
standings export (a person's own downloaded "Export to CSV" from a
contest they entered) against that week's already-uploaded DK salary
file to show the top-finishing lineups (with Exp Pts vs. Act Pts) and a
reformatted per-player results file. See contest_standings_parser.py's
docstring for the raw file's own column layout.
"""

from fastapi import APIRouter

from backend.api.contest_results.file_info import router as file_info_router
from backend.api.contest_results.import_csv import router as import_csv_router
from backend.api.contest_results.player_results import router as player_results_router
from backend.api.contest_results.top_lineups import router as top_lineups_router

router = APIRouter(prefix="/contest-results")
router.include_router(import_csv_router)
router.include_router(top_lineups_router)
router.include_router(player_results_router)
router.include_router(file_info_router)
