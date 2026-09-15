"""
GET /latest?season=&week=&platform= (mounted at /api/player-pool/latest --
see backend/api/player_pool/__init__.py). The shared DK salary snapshot
(see backend/api/dk_salary/import_csv.py) is the required player universe
-- unlike Ownership, this tab doesn't depend on the Ownership tab having
loaded anything for the week. Every player is enriched with ownership_pct
(opportunistically merged in from the Ownership tab's snapshot, if one
exists for the same week) and depth_rank (see
backend/services/player_pool/enrichment.py's enrich_players_for_week) --
that merge is best-effort, not a requirement, so a 404 here only ever
means "no DK salary file uploaded yet." `platform` (default "DraftKings")
picks which platform's raw salary file gets loaded -- see
backend/services/platform_settings/prefix.py.

Also filters out any QB/RB/WR/TE that Settings' Player Selection grid has
narrowed out for this (season, week, platform) -- see
backend/services/player_selection/engine.py's filter_selected_players --
*unless* the caller passes apply_selection_filter=false. The Player Pool
tab always wants this filter (that's the whole point of Player Selection);
Settings' own Player Default Settings grid deliberately opts out, since
that panel is meant to be independent of Player Selection and instead
narrows by its own depth-chart cutoff (depth_rank, below) -- a player unchecked
in Player Selection should still get a Volume/Talent baseline here. DST is
never filtered by this either way. My Player Pool's own /latest endpoint
(backend/api/my_player_pool/latest.py) opts out of this filter entirely
and applies its own, unrelated membership filter instead -- see that
module's docstring.

Whether an Ownership snapshot was found at all (not just whether any given
player matched one) is passed through to compute_player_pool as
ownership_retrieved -- see that function's docstring for why a player
absent from an otherwise-real snapshot displays as 0% owned rather than
blank.

The platform's Salary Multiplier (Settings' Salary Multiplier field, or
its computed default if never explicitly set -- see backend/services/
salary_multiplier/engine.py) is resolved here and passed into
compute_player_pool so every row's expected_fpts uses the right
multiplier for `platform`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.player_selection.player_selection_repo import load_overrides
from backend.repositories.salary_multiplier.salary_multiplier_repo import load_multipliers
from backend.schemas.player_pool.player_pool import PlayerPoolResult
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.player_pool.engine import compute_player_pool
from backend.services.player_pool.enrichment import enrich_players_for_week
from backend.services.player_selection.engine import filter_selected_players
from backend.services.salary_multiplier.engine import resolve_multiplier

router = APIRouter()


@router.get("/latest", response_model=PlayerPoolResult)
def player_pool_latest_endpoint(
    season: int,
    week: int,
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    apply_selection_filter: bool = True,
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
    players, ownership_retrieved = enrich_players_for_week(
        salary_snapshot.players, season, week, platform, settings.nfl_data_dir
    )

    if apply_selection_filter:
        overrides = load_overrides(settings.nfl_data_dir, season, week, platform, contest)
        players = filter_selected_players(players, overrides)

    saved_multiplier = load_multipliers(settings.salary_multiplier_dir).get(platform)

    return compute_player_pool(
        players,
        season,
        week,
        platform,
        settings.game_environment_dir,
        settings.nfl_data_dir,
        # True whenever an Ownership snapshot exists for this (season,
        # week), regardless of whether any given player showed up in it --
        # lets compute_player_pool tell "ownership not retrieved yet"
        # (ownership_pct stays None) apart from "retrieved, this player
        # just isn't projected to be owned" (ownership_pct becomes 0.0).
        ownership_retrieved=ownership_retrieved,
        multiplier=resolve_multiplier(platform, saved_multiplier),
        name_aliases_json=settings.name_aliases_json,
    )
