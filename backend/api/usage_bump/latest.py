"""
GET /opportunities/latest -- computes compute_usage_bumps() live against
the most recently saved depth-chart snapshot, merging in the three
usage-bump config files (see engine.py's docstring for how they fit
together). No persistence, and no query-param filtering here --
team/position/status filtering happens client-side in the frontend, same
as the diff page.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import (
    find_latest_snapshot,
    load_snapshot,
    snapshot_id_from_path,
)
from backend.repositories.usage_bump.position_settings_repo import load_usage_bump_position_settings
from backend.repositories.usage_bump.scoring_matrix_repo import load_bump_matrix
from backend.repositories.usage_bump.usage_bump_players_repo import load_usage_bump_players
from backend.schemas.usage_bump.usage_bump import UsageBump
from backend.services.usage_bump.engine import compute_usage_bumps

router = APIRouter()


class UsageBumpsResult(BaseModel):
    snapshot_id: str
    scraped_at: str
    usage_bumps: list[UsageBump]


@router.get("/latest", response_model=UsageBumpsResult)
def usage_bump_latest_endpoint() -> UsageBumpsResult:
    snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    if snapshot_path is None:
        raise HTTPException(
            status_code=404,
            detail="No snapshots yet -- run POST /api/depth-charts/scrape first.",
        )

    snapshot = load_snapshot(snapshot_path)
    usage_bump_players = load_usage_bump_players(settings.usage_bump_players_json)
    position_settings = load_usage_bump_position_settings(settings.usage_bump_position_settings_json)
    matrix = load_bump_matrix(settings.player_out_settings_json)

    return UsageBumpsResult(
        snapshot_id=snapshot_id_from_path(snapshot_path),
        scraped_at=snapshot.scraped_at,
        usage_bumps=compute_usage_bumps(snapshot, usage_bump_players, position_settings, matrix),
    )
