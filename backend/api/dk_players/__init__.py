from fastapi import APIRouter

from backend.api.dk_players.add_week import router as add_week_router
from backend.api.dk_players.calculate_week import router as calculate_week_router
from backend.api.dk_players.list_players import router as list_players_router
from backend.api.dk_players.week_status import router as week_status_router
from backend.api.dk_players.weekly_stats import router as weekly_stats_router

router = APIRouter(prefix="/dk-players")
router.include_router(list_players_router)
router.include_router(week_status_router)
router.include_router(add_week_router)
router.include_router(calculate_week_router)
router.include_router(weekly_stats_router)
