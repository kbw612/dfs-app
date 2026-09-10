"""
GET /latest?season=&week=&platform=&contest= (mounted at
/api/my-player-pool/latest -- see backend/api/my_player_pool/__init__.py).
Returns exactly the players explicitly added to My Player Pool for this
(season, week, platform, contest), each with the same full computed row
(salary, Total, every
score field, ownership_pct, depth_rank, etc.) the Player Rankings tab
shows -- built by enriching the whole salary file the same way Player
Pool does (see backend/services/player_pool/enrichment.py), narrowing
that down to just this tab's own saved membership list, and running the
result through the same compute_player_pool() Player Rankings uses, so
the two tabs' numbers always agree for a shared player.

My Player Pool is deliberately independent of Settings' Player Selection
narrowing -- a player can be added here whether or not they're checked in
Player Selection (see backend/schemas/my_player_pool/my_player_pool.py) --
so this endpoint never applies filter_selected_players, unlike Player
Pool's own /latest. Same 404 as Player Pool/Player Selection if no DK
salary file has been uploaded yet for this week.

Same Salary Multiplier resolution as Player Pool's /latest -- see that
module's docstring -- so expected_fpts agrees between the two tabs for a
shared player.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.my_player_pool.my_player_pool_repo import load_membership
from backend.repositories.salary_multiplier.salary_multiplier_repo import load_multipliers
from backend.schemas.player_pool.player_pool import PlayerPoolResult
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.my_player_pool.engine import in_my_player_pool
from backend.services.player_pool.engine import compute_player_pool
from backend.services.player_pool.enrichment import enrich_players_for_week
from backend.services.salary_multiplier.engine import resolve_multiplier

router = APIRouter()


@router.get("/latest", response_model=PlayerPoolResult)
def my_player_pool_latest_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"
) -> PlayerPoolResult:
    try:
        csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=f"No DK salary file uploaded yet for season {season} week {week} -- upload this week's DK salary export first.",
        )
    salary_snapshot, _messages = parse_dk_salary_csv(csv_text, season, week)
    players, ownership_retrieved = enrich_players_for_week(salary_snapshot.players, season, week)

    membership = load_membership(settings.nfl_data_dir, season, week, platform, contest)
    players = [p for p in players if in_my_player_pool(p.player, membership)]

    saved_multiplier = load_multipliers(settings.salary_multiplier_dir).get(platform)

    return compute_player_pool(
        players,
        season,
        week,
        platform,
        settings.game_environment_dir,
        settings.nfl_data_dir,
        ownership_retrieved=ownership_retrieved,
        multiplier=resolve_multiplier(platform, saved_multiplier),
    )
