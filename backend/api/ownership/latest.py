"""
GET /latest?season=&week= (mounted at /api/ownership/latest -- see
backend/api/ownership/__init__.py). Loads the most recently saved
ownership snapshot for that (season, week) and computes all four derived
views live, on request -- see backend/services/ownership/engine.py for
compute_high_owned()/compute_game_leverage()/compute_pivots()/
compute_multi_leverage(). Nothing here is pre-computed or persisted, same
philosophy as usage_bump/latest.py and depth_charts/diff.py.

Before computing any of the derived views, every player is enriched with
its depth-chart rank (see depth_rank.py) by cross-referencing the latest
*depth-chart* snapshot -- a completely separate resource/scrape from
ownership. This happens once, here, on the raw player list; the derived
views below just filter/group those same enriched OwnershipPlayer objects,
so `rank` shows up automatically in `players`, `high_owned`,
`game_leverage`, `pivots`, and `multi_leverage` alike without engine.py
needing to know anything about depth charts.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot as find_latest_depth_chart_snapshot
from backend.repositories.depth_charts.snapshot_repo import load_snapshot as load_depth_chart_snapshot
from backend.repositories.ownership.leverage_tiers_repo import load_leverage_tiers
from backend.repositories.ownership.snapshot_repo import find_latest_snapshot, load_snapshot, snapshot_id_from_path
from backend.schemas.ownership.ownership import GameLeverageGroup, MultiLeveragePlayer, OwnershipPlayer, PivotGroup
from backend.services.ownership.depth_rank import build_depth_rank_lookup
from backend.services.ownership.engine import (
    compute_game_leverage,
    compute_high_owned,
    compute_multi_leverage,
    compute_pivots,
)

router = APIRouter()


def _enrich_with_depth_rank(players: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
    depth_snapshot_path = find_latest_depth_chart_snapshot(settings.snapshots_dir)
    depth_snapshot = load_depth_chart_snapshot(depth_snapshot_path) if depth_snapshot_path else None
    rank_lookup = build_depth_rank_lookup(depth_snapshot)
    return [player.model_copy(update={"rank": rank_lookup.get(player.player)}) for player in players]


class OwnershipLatestResult(BaseModel):
    snapshot_id: str
    scraped_at: str
    season: int
    week: int
    leverage_point: float
    players: list[OwnershipPlayer]
    high_owned: list[OwnershipPlayer]
    game_leverage: list[GameLeverageGroup]
    pivots: list[PivotGroup]
    multi_leverage: list[MultiLeveragePlayer]


@router.get("/latest", response_model=OwnershipLatestResult)
def ownership_latest_endpoint(season: int, week: int) -> OwnershipLatestResult:
    snapshot_path = find_latest_snapshot(settings.ownership_snapshots_dir, season=season, week=week)
    if snapshot_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ownership snapshots yet for season {season} week {week} -- run POST /api/ownership/scrape first.",
        )

    snapshot = load_snapshot(snapshot_path)
    tiers = load_leverage_tiers(settings.ownership_leverage_tiers_json)

    players = _enrich_with_depth_rank(snapshot.players)
    high_owned, leverage_point = compute_high_owned(players, tiers)
    game_leverage = compute_game_leverage(players, leverage_point)
    pivots = compute_pivots(players)

    return OwnershipLatestResult(
        snapshot_id=snapshot_id_from_path(snapshot_path),
        scraped_at=snapshot.scraped_at,
        season=snapshot.season,
        week=snapshot.week,
        leverage_point=leverage_point,
        players=players,
        high_owned=high_owned,
        game_leverage=game_leverage,
        pivots=pivots,
        multi_leverage=compute_multi_leverage(pivots, game_leverage),
    )
