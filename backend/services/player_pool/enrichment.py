"""
Shared "enrich this week's salary-file player list with reference data"
step, used by both Player Pool's and My Player Pool's /latest endpoints
(see backend/api/player_pool/latest.py and
backend/api/my_player_pool/latest.py) before each applies its own,
different membership filter on top -- Player Selection's checkboxes for
Player Pool, My Player Pool's own saved shortlist for that tab. Factored
out here once a second caller needed the exact same two enrichments,
rather than duplicated in both endpoint files.

ownership_pct comes from the same Settings-uploaded projections file
(backend/repositories/ownership/projections_repo.py) that the Ownership
tab's own /api/ownership/latest reads (see backend/api/ownership/
latest.py) -- this used to read the older, separate OwnershipSnapshot
scrape/mock-CSV pipeline (backend/repositories/ownership/snapshot_repo.py)
instead, back when Ownership Pivots read that same pipeline too. That tab
was migrated to the Settings-uploaded file so Ownership Summary and
Pivots would always agree; this module wasn't migrated at the same time,
which went unnoticed because a snapshot file "existing" (even an empty
one) was enough to mark ownership_retrieved=True and quietly resolve
every player to the 0.0 "retrieved but absent" fallback instead of
erroring -- every 2026 week 1 snapshot on disk turned out to be an empty
stub from a mock-import endpoint nothing in the UI actually calls
anymore, which is why every player's ownership showed as flat 0% (Boom/
Bust and Player Rankings both, since both flow through this function).
Now reads the same real, currently-uploaded file the Ownership tab does,
so there's one source of truth for "what's this week's ownership" app-
wide.
"""

from __future__ import annotations

from pathlib import Path

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot as find_latest_depth_chart_snapshot
from backend.repositories.depth_charts.snapshot_repo import load_snapshot as load_depth_chart_snapshot
from backend.repositories.ownership.projections_repo import load_projections_csv
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct
from backend.services.ownership.csv_loader import parse_ownership_projections_csv
from backend.services.ownership.depth_rank import build_depth_rank_lookup
from backend.services.shared.name_match import normalize_player_name


def enrich_players_for_week(
    players: list[OwnershipPlayer], season: int, week: int, platform: str, nfl_data_dir: Path
) -> tuple[list[OwnershipPlayer], bool]:
    """(enriched_players, ownership_retrieved).

    Merges in ownership_pct from this (season, week, platform)'s current
    Ownership projections upload, if one exists (best-effort, by player
    name -- see ownership_enrich.enrich_with_ownership_pct), and
    depth_rank from the latest depth-chart snapshot (app-wide, not scoped
    per week -- see ownership/depth_rank.py).

    ownership_retrieved is True whenever a projections file has been
    uploaded at all for this (season, week, platform), regardless of
    whether any given player showed up in it -- callers pass this
    straight through to compute_player_pool so a player absent from an
    otherwise-real upload resolves to 0% owned rather than staying blank
    (see that function's own docstring)."""
    projections_csv = load_projections_csv(nfl_data_dir, season, week, platform)
    ownership_players = parse_ownership_projections_csv(projections_csv)[0] if projections_csv is not None else None
    enriched = enrich_with_ownership_pct(players, ownership_players)

    depth_snapshot_path = find_latest_depth_chart_snapshot(settings.snapshots_dir)
    depth_snapshot = load_depth_chart_snapshot(depth_snapshot_path) if depth_snapshot_path else None
    rank_lookup = build_depth_rank_lookup(depth_snapshot)
    enriched = [
        player.model_copy(update={"depth_rank": rank_lookup.get(normalize_player_name(player.player))})
        for player in enriched
    ]
    return enriched, ownership_players is not None
