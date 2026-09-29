"""
Shared "combined ownership% for one team" calculation -- DST excluded, a
player missing ownership_pct contributes 0 rather than being skipped. Used
by both Game Preview's own team_projected_ownership_pct (backend/services/
game_preview/game_preview_matchups.py) and the Ownership Summary tab's own
per-team/per-game rollups (backend/services/ownership/ownership_summary.py),
so "how much combined ownership does this team carry" means exactly the
same thing on both tabs -- this one function is the single source of
truth, not two independently hand-copied implementations that could drift
apart from each other.

None is returned only when the team has zero matching (non-DST) rows at
all -- distinct from a real computed total that happens to sum to 0.0.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.schemas.ownership.ownership import OwnershipPlayer


def sum_current_ownership_pct(team: str, players: Iterable[OwnershipPlayer]) -> float | None:
    matching = [p for p in players if p.team == team and p.position != "DST"]
    if not matching:
        return None
    return sum(p.ownership_pct or 0.0 for p in matching)
