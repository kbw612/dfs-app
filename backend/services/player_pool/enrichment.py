"""
Shared "enrich this week's salary-file player list with reference data"
step, used by both Player Pool's and My Player Pool's /latest endpoints
(see backend/api/player_pool/latest.py and
backend/api/my_player_pool/latest.py) before each applies its own,
different membership filter on top -- Player Selection's checkboxes for
Player Pool, My Player Pool's own saved shortlist for that tab. Factored
out here once a second caller needed the exact same two enrichments,
rather than duplicated in both endpoint files.
"""

from __future__ import annotations

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot as find_latest_depth_chart_snapshot
from backend.repositories.depth_charts.snapshot_repo import load_snapshot as load_depth_chart_snapshot
from backend.repositories.ownership.snapshot_repo import (
    find_latest_snapshot as find_latest_ownership_snapshot,
    load_snapshot as load_ownership_snapshot,
)
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct
from backend.services.ownership.depth_rank import build_depth_rank_lookup
from backend.services.shared.name_match import normalize_player_name


def enrich_players_for_week(players: list[OwnershipPlayer], season: int, week: int) -> tuple[list[OwnershipPlayer], bool]:
    """(enriched_players, ownership_retrieved).

    Merges in ownership_pct from the Ownership tab's snapshot for this
    (season, week) if one exists (best-effort, by player name -- see
    ownership_enrich.enrich_with_ownership_pct), and depth_rank from the
    latest depth-chart snapshot (app-wide, not scoped per week -- see
    ownership/depth_rank.py).

    ownership_retrieved is True whenever an Ownership snapshot was found
    at all for this (season, week), regardless of whether any given
    player showed up in it -- callers pass this straight through to
    compute_player_pool so a player absent from an otherwise-real
    snapshot resolves to 0% owned rather than staying blank (see that
    function's own docstring)."""
    ownership_snapshot_path = find_latest_ownership_snapshot(settings.ownership_snapshots_dir, season=season, week=week)
    ownership_players = load_ownership_snapshot(ownership_snapshot_path).players if ownership_snapshot_path else None
    enriched = enrich_with_ownership_pct(players, ownership_players)

    depth_snapshot_path = find_latest_depth_chart_snapshot(settings.snapshots_dir)
    depth_snapshot = load_depth_chart_snapshot(depth_snapshot_path) if depth_snapshot_path else None
    rank_lookup = build_depth_rank_lookup(depth_snapshot)
    enriched = [
        player.model_copy(update={"depth_rank": rank_lookup.get(normalize_player_name(player.player))})
        for player in enriched
    ]
    return enriched, ownership_players is not None
