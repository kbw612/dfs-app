"""
GET /dst-trends?season=&week=&window_weeks= (mounted at /api/dst-trends --
see backend/api/dst_trends/__init__.py). Backs the DST Trends tab -- see
backend/services/dst_trends/dst_trends_engine.py for the full computation.

Reads only FantasyData_DSTs.csv (via the same weekly_stats_repo/
weekly_stats_loader this app already uses for DK Players/Game Logs) --
no DK Players tracker, Schedule, or Salary file needed, since both
leaderboards are entirely derived from that one file's own TEAM/OPP/
DEF_SCK/DEF_INT/FR columns (see the engine's own docstring). No
platform/contest params either -- these are league-wide stats, same
reasoning as weekly_stats_repo.py's own "no platform dimension" note.

404 only when the DST file hasn't been scraped for this season at all --
same "nothing to show" convention as every other tab here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_players.weekly_stats_repo import load_weekly_stats_csv
from backend.schemas.dst_trends.dst_trends import DstTrendsResult
from backend.services.dk_players.weekly_stats_loader import load_weekly_stat_lines
from backend.services.dst_trends.dst_trends_engine import build_dst_trend_leaderboards

router = APIRouter()


@router.get("/dst-trends", response_model=DstTrendsResult)
def dst_trends_endpoint(season: int, week: int, window_weeks: int = 5) -> DstTrendsResult:
    dst_csv = load_weekly_stats_csv(settings.nfl_data_dir, season, "DST")
    if dst_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No DST weekly stats scraped yet for season {season} -- "
                'run "Scrape Weekly Stats" on the Settings tab first.'
            ),
        )
    dst_stat_lines = load_weekly_stat_lines(dst_csv)
    return build_dst_trend_leaderboards(dst_stat_lines, season, week, window_weeks)
