"""
GET /game-logs-against?season=&week=&platform=&lookback_weeks= (mounted at
/api/game-logs-against -- see backend/api/game_logs_against/__init__.py).
Backs the Game Logs Against tab -- see backend/services/game_logs/
game_logs_against_engine.py for the full computation.

Unlike /api/game-logs, this endpoint IS scoped to the current week's slate:
it computes one "Against {team}" panel per team appearing in this week's
games (same games list build_game_options already returns for Game Logs'
own Game filter), matching the person's own reference script, which only
ever processed the teams in `flat_teams` for the week at hand rather than
all 32 teams league-wide. Selecting a game client-side then just filters
down to that game's two teams' panels -- no separate per-team backend call
needed (see the "Game filter shows both teams" design decision this
endpoint's rows already support via each row's own `against_team` field).

Only needs the DK Players tracker + Schedule file (no FantasyData weekly
stats -- see game_logs_against.py's own docstring for why). Same 404
convention as /api/game-logs: no tracker rows at all yet for this
(season, platform) means there's nothing to show. Missing Schedule data
degrades gracefully to an empty `games` list and no rows (every team's
own schedule window is then empty), same as Game Logs.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.schemas.game_logs.game_logs_against import GameLogsAgainstResult
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv
from backend.services.game_logs.game_logs_against_engine import build_game_logs_against_rows
from backend.services.game_logs.game_logs_engine import build_game_options
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


@router.get("/game-logs-against", response_model=GameLogsAgainstResult)
def game_logs_against_endpoint(
    season: int, week: int, platform: str = "DraftKings", lookback_weeks: int = 6
) -> GameLogsAgainstResult:
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

    games = build_game_options(schedule_rows, week)
    teams = sorted({team for game in games for team in game.teams})

    rows = []
    for team in teams:
        rows.extend(build_game_logs_against_rows(tracker_rows, schedule_rows, team, week, lookback_weeks))

    return GameLogsAgainstResult(
        season=season,
        week=week,
        lookback_weeks=lookback_weeks,
        games=games,
        rows=rows,
    )
