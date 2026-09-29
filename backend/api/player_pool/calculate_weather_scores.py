"""
POST /calculate-weather-scores?season=&week=&platform=&contest= (mounted at
/api/player-pool/calculate-weather-scores -- see backend/api/player_pool/
__init__.py). Bulk-computes each DST's Weather score from its own game's
Weather note and saves it as that (season, week, platform)'s Weather
override for every eligible DST, wholesale-replacing whatever Weather value
was saved before for them -- "latest applied wins," same philosophy as
calculate_ownership_scores.py. Weather is DST-only (see backend/schemas/
player_pool/player_pool.py's weather docstring) -- offense rows are never
scored here, and don't count toward applied/skipped either way.

A DST whose game has no notable Weather note this week (the common case --
see backend/schemas/weather/weather.py's WeatherSnapshot docstring: only
games someone actually flagged appear there) doesn't count as "applied,"
and rolls into `skipped_count` -- same as an offense player with no
ownership_pct in calculate_ownership_scores.py.

404s if no DK salary file exists yet for this (season, week, platform,
contest) (no player universe to iterate). Unlike calculate_ownership_scores,
a missing Weather snapshot for the week is NOT an error -- it just means
every DST is skipped (no notable weather at all that week is a normal,
common state, not a missing-upload error state).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.player_pool.entries_repo import save_weather_scores
from backend.repositories.weather.weather_repo import load_weather
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.ownership.position_blocks import game_key
from backend.services.weather.scoring import score_weather_color

router = APIRouter()


class WeatherScoresApplyResult(BaseModel):
    season: int
    week: int
    applied_count: int
    skipped_count: int


@router.post("/calculate-weather-scores", response_model=WeatherScoresApplyResult)
def calculate_weather_scores_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"
) -> WeatherScoresApplyResult:
    try:
        csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No DK salary file uploaded yet for season {season} week {week} -- "
                "upload this week's DK salary export first."
            ),
        )

    salary_snapshot, _messages = parse_dk_salary_csv(csv_text, season, week)
    weather = load_weather(settings.nfl_data_dir, season, week)
    weather_by_key = {g.game_key: g for g in weather.games} if weather is not None else {}

    scores: dict[str, float] = {}
    skipped_count = 0
    for player in salary_snapshot.players:
        if player.position != "DST":
            continue
        game_id = "-".join(sorted(game_key(player)))
        game = weather_by_key.get(game_id)
        if game is None:
            skipped_count += 1
            continue
        scores[player.player] = score_weather_color(game.color)

    save_weather_scores(settings.nfl_data_dir, season, week, platform, scores)

    return WeatherScoresApplyResult(season=season, week=week, applied_count=len(scores), skipped_count=skipped_count)
