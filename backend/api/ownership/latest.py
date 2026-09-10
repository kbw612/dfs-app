"""
GET /latest?season=&week=&platform= (mounted at /api/ownership/latest --
see backend/api/ownership/__init__.py). Loads the *current* ownership
projections file uploaded via the Settings tab (see backend/repositories/
ownership/projections_repo.py -- the same file GET /api/ownership/
projections reads for the Ownership Summary tab, not the separate
initial/baseline file that feature also tracks) and computes all four
derived views live, on request -- see backend/services/ownership/engine.py
for compute_high_owned()/compute_game_leverage()/compute_pivots()/
compute_multi_leverage(). Nothing here is pre-computed or persisted, same
philosophy as usage_bump/latest.py and depth_charts/diff.py.

This used to read the older mock-scrape OwnershipSnapshot (see
backend/repositories/ownership/snapshot_repo.py) -- Ownership Pivots now
reads the same Settings-uploaded file as Ownership Summary instead, so
both tabs always agree on "what's the latest ownership data" and there's
no separate "Load ownership data" step anymore; whatever's currently
uploaded in Settings is what this endpoint returns. Player Pool/Salary
Blocks still read the older OwnershipSnapshot for their own ownership_pct
enrichment (see backend/services/player_pool/enrichment.py) -- that's a
separate, untouched consumer of the old pipeline. `platform` defaults to
"DraftKings", same convention as every other platform-scoped endpoint.

Before computing any of the derived views, every player is enriched with
its depth-chart rank (see depth_rank.py) by cross-referencing the latest
*depth-chart* snapshot -- a completely separate resource/scrape from
ownership. This happens once, here, on the raw player list; the derived
views below just filter/group those same enriched OwnershipPlayer objects,
so `depth_rank` shows up automatically in `players`, `high_owned`,
`game_leverage`, `pivots`, and `multi_leverage` alike without engine.py
needing to know anything about depth charts.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot as find_latest_depth_chart_snapshot
from backend.repositories.depth_charts.snapshot_repo import load_snapshot as load_depth_chart_snapshot
from backend.repositories.ownership.leverage_tiers_repo import load_leverage_tiers
from backend.repositories.ownership.projections_repo import load_projections_csv, projections_csv_path
from backend.schemas.ownership.ownership import GameLeverageGroup, MultiLeveragePlayer, OwnershipPlayer, PivotGroup
from backend.services.ownership.csv_loader import parse_ownership_projections_csv
from backend.services.ownership.depth_rank import build_depth_rank_lookup
from backend.services.ownership.engine import (
    compute_game_leverage,
    compute_high_owned,
    compute_multi_leverage,
    compute_pivots,
)
from backend.services.shared.name_match import normalize_player_name

router = APIRouter()


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def _enrich_with_depth_rank(players: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
    depth_snapshot_path = find_latest_depth_chart_snapshot(settings.snapshots_dir)
    depth_snapshot = load_depth_chart_snapshot(depth_snapshot_path) if depth_snapshot_path else None
    rank_lookup = build_depth_rank_lookup(depth_snapshot)
    return [
        player.model_copy(update={"depth_rank": rank_lookup.get(normalize_player_name(player.player))})
        for player in players
    ]


class OwnershipLatestResult(BaseModel):
    uploaded_at: str
    season: int
    week: int
    leverage_point: float
    players: list[OwnershipPlayer]
    high_owned: list[OwnershipPlayer]
    game_leverage: list[GameLeverageGroup]
    pivots: list[PivotGroup]
    multi_leverage: list[MultiLeveragePlayer]


@router.get("/latest", response_model=OwnershipLatestResult)
def ownership_latest_endpoint(season: int, week: int, platform: str = "DraftKings") -> OwnershipLatestResult:
    try:
        current_path = projections_csv_path(settings.nfl_data_dir, season, week, platform)
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
    tiers = load_leverage_tiers(settings.ownership_leverage_tiers_json)

    players = _enrich_with_depth_rank(raw_players)
    high_owned, leverage_point = compute_high_owned(players, tiers)
    game_leverage = compute_game_leverage(players, leverage_point)
    pivots = compute_pivots(players)

    return OwnershipLatestResult(
        uploaded_at=_mtime_iso(current_path),
        season=season,
        week=week,
        leverage_point=leverage_point,
        players=players,
        high_owned=high_owned,
        game_leverage=game_leverage,
        pivots=pivots,
        multi_leverage=compute_multi_leverage(pivots, game_leverage),
    )
