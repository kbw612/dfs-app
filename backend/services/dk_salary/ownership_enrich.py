"""
Cross-references the shared DK salary snapshot's player list (see
dk_salary_loader.py) against the Ownership tab's own snapshot, by player
name, to opportunistically fill in ownership_pct for display. Salary
Blocks and Player Pool no longer *require* the Ownership snapshot to exist
(that's the point of having one shared salary upload independent of it),
but both still show this reference figure when the Ownership tab happens
to have loaded one for the same week -- same "name match only, no
player_id yet" tradeoff as depth_rank.py's rank cross-reference.
"""

from __future__ import annotations

from typing import Optional

from backend.schemas.ownership.ownership import OwnershipPlayer


def enrich_with_ownership_pct(
    players: list[OwnershipPlayer], ownership_players: Optional[list[OwnershipPlayer]]
) -> list[OwnershipPlayer]:
    if not ownership_players:
        return players

    pct_by_name = {p.player: p.ownership_pct for p in ownership_players if p.ownership_pct is not None}
    return [
        player.model_copy(update={"ownership_pct": pct_by_name[player.player]}) if player.player in pct_by_name else player
        for player in players
    ]
