"""
GET /latest?season=&week=&platform= (mounted at /api/player-pool/latest --
see backend/api/player_pool/__init__.py). The shared DK salary snapshot
(see backend/api/dk_salary/import_csv.py) is the required player universe
-- unlike Ownership, this tab doesn't depend on the Ownership tab having
loaded anything for the week. If the Ownership tab *does* happen to have a
snapshot for the same (season, week), its ownership_pct values get
opportunistically merged in by player name (see
dk_salary.ownership_enrich.enrich_with_ownership_pct) purely for display
-- that merge is best-effort, not a requirement, so a 404 here only ever
means "no DK salary file uploaded yet." `platform` (default "DraftKings")
picks which platform's raw salary file gets loaded -- see
backend/services/platform_settings/prefix.py.

Also filters out any QB/RB/WR/TE that Settings' Player Selection grid has
narrowed out for this (season, week, platform) -- see
backend/services/player_selection/engine.py's filter_selected_players.
DST is never filtered by this.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.ownership.snapshot_repo import (
    find_latest_snapshot as find_latest_ownership_snapshot,
    load_snapshot as load_ownership_snapshot,
)
from backend.repositories.player_selection.player_selection_repo import load_overrides
from backend.schemas.player_pool.player_pool import PlayerPoolResult
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct
from backend.services.player_pool.engine import compute_player_pool
from backend.services.player_selection.engine import filter_selected_players

router = APIRouter()


@router.get("/latest", response_model=PlayerPoolResult)
def player_pool_latest_endpoint(season: int, week: int, platform: str = "DraftKings") -> PlayerPoolResult:
    try:
        csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=f"No DK salary file uploaded yet for season {season} week {week} -- upload this week's DK salary export first.",
        )
    salary_snapshot, _messages = parse_dk_salary_csv(csv_text, season, week)

    ownership_snapshot_path = find_latest_ownership_snapshot(settings.ownership_snapshots_dir, season=season, week=week)
    ownership_players = load_ownership_snapshot(ownership_snapshot_path).players if ownership_snapshot_path else None
    players = enrich_with_ownership_pct(salary_snapshot.players, ownership_players)

    overrides = load_overrides(settings.nfl_data_dir, season, week, platform)
    players = filter_selected_players(players, overrides)

    return compute_player_pool(
        players, season, week, settings.player_pool_dir, settings.game_environment_dir, settings.player_attributes_dir
    )
