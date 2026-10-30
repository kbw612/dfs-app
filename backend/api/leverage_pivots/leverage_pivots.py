"""
GET /leverage-pivots?season=&week=&platform=&player=&position= (mounted at
/api/leverage-pivots). Reads the same Settings-uploaded ownership projections
file as Ownership Pivots and returns the whole Leverage & Pivots tab finished:
chalk chips (`chalk_pct`, default 15% -- owned at or above it), the
multi-reason panel (every owned player is a trigger; `min_reasons`, default 3, is the fewest reasons a listed player needs), and -- when `player` is given -- the four columns for
that player, narrowed to `position` when set. See
backend/services/leverage_pivots/engine.py for the rules.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.ownership.projections_repo import load_projections_csv
from backend.schemas.leverage_pivots.leverage_pivots import LeveragePivotsResult
from backend.services.leverage_pivots.engine import (
    build_chalk_groups,
    build_panel,
    build_selected,
    owned_players,
)
from backend.services.ownership.csv_loader import parse_ownership_projections_csv
from backend.services.shared.name_match import normalize_player_name

router = APIRouter()


@router.get("/leverage-pivots", response_model=LeveragePivotsResult)
def leverage_pivots_endpoint(
    season: int,
    week: int,
    platform: str = "DraftKings",
    player: str | None = None,
    position: str | None = None,
    chalk_pct: float = 15.0,
    min_reasons: int = 3,
) -> LeveragePivotsResult:
    try:
        csv_text = load_projections_csv(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No ownership projections file uploaded yet for season {season} week {week} -- "
                "upload it in the Settings tab."
            ),
        )
    raw_players, _messages = parse_ownership_projections_csv(csv_text)
    if not 0 <= chalk_pct <= 100:
        raise HTTPException(status_code=400, detail="chalk_pct must be between 0 and 100")
    leverage_point = chalk_pct

    players = owned_players(raw_players)
    chalk = [p for p in players if p.ownership_pct >= leverage_point]

    result = LeveragePivotsResult(
        season=season,
        week=week,
        leverage_point=leverage_point,
        chalk=build_chalk_groups(chalk),
        panel=build_panel(players, leverage_point, min_reasons),
        search_names=[p.player for p in sorted(players, key=lambda p: p.ownership_pct, reverse=True)],
    )
    if player:
        wanted = normalize_player_name(player)
        match = next((p for p in players if normalize_player_name(p.player) == wanted), None)
        if match is None:
            result.selected_not_found = True
        else:
            result.selected = build_selected(match, players, leverage_point, position)
    return result
