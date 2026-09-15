"""
GET /game-logs?season=&week=&platform=&lookback_weeks= (mounted at
/api/game-logs -- see backend/api/game_logs/__init__.py). Backs the Game
Logs tab -- see backend/services/game_logs/game_logs_engine.py for the
full computation. Returns every QB/RB/WR/TE currently rostered (per the
DK Players tracker) league-wide, not scoped to a single team/game --
same convention as every other tab's Position filter (My Player Pool,
Ownership Summary, ...), where the frontend's own Team/Game chip filters
narrow the full list rather than the backend accepting filter params.

Gracefully degrades when either side-channel source is missing: no
Schedule file uploaded yet just means every row's opponent/game_location
come back None (empty `games` list too, so the Game filter has nothing to
offer) and no FantasyData weekly stats uploaded for a position just means
that position's Touch/Targets/etc. come back None -- neither blocks the
FPTS/Non_TD_FPTS/TD_FPTS/Multiplier columns, which only need the DK
Players tracker itself. 404 only if the tracker has no rows at all yet
for this (season, platform) -- there's nothing to show at all in that
case, same as every other "nothing uploaded yet" 404 in this app.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.repositories.dk_players.weekly_stats_repo import load_weekly_stats_csv
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.schemas.game_logs.game_logs import GameLogsResult
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv
from backend.services.dk_players.weekly_stats_loader import load_weekly_stat_lines
from backend.services.game_logs.game_logs_engine import POSITIONS, build_game_log_rows, build_game_options
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


@router.get("/game-logs", response_model=GameLogsResult)
def game_logs_endpoint(
    season: int, week: int, platform: str = "DraftKings", lookback_weeks: int = 6
) -> GameLogsResult:
    tracker_csv = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    if tracker_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No DK Players tracker started yet for season {season} -- "
                'run "Add Week Players" on the DK Players tab first.'
            ),
        )
    tracker_rows = parse_dk_players_csv(tracker_csv)

    schedule_csv = load_schedule_csv(settings.nfl_data_dir, season)
    schedule_rows = parse_schedule_csv(schedule_csv) if schedule_csv is not None else []

    stat_lines_by_position = {}
    for position in POSITIONS:
        stats_csv = load_weekly_stats_csv(settings.nfl_data_dir, season, position)
        stat_lines_by_position[position] = load_weekly_stat_lines(stats_csv) if stats_csv is not None else {}

    rows, reference_week = build_game_log_rows(tracker_rows, schedule_rows, stat_lines_by_position, week, lookback_weeks)
    games = build_game_options(schedule_rows, week)

    return GameLogsResult(
        season=season,
        week=week,
        reference_week=reference_week,
        lookback_weeks=lookback_weeks,
        games=games,
        rows=rows,
    )
