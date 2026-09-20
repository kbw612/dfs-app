"""
Cross-references the shared DK salary snapshot's player list (see
dk_salary_loader.py) against the Ownership tab's own snapshot, to
opportunistically fill in ownership_pct for display. Salary Blocks and
Player Pool no longer *require* the Ownership snapshot to exist (that's
the point of having one shared salary upload independent of it), but both
still show this reference figure when the Ownership tab happens to have
loaded one for the same week -- same "best-effort match only, no
player_id yet" tradeoff as depth_rank.py's rank cross-reference.

Offense matches by exact player name, same as always. DST is matched by
team abbreviation instead: DK's own salary export names a DST by its
nickname alone (e.g. "Ravens"), while the Ownership projections file (an
external, differently-formatted source) spells it out in full (e.g.
"Baltimore Ravens") -- an exact-name match between those two would always
miss, silently leaving every DST's ownership_pct unset. Both sides already
carry a normalized `team` field (see services/ownership/parsing.py's
normalize_team_abbrev), so matching DST rows on that instead sidesteps the
naming mismatch entirely.
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
    pct_by_dst_team = {
        p.team: p.ownership_pct for p in ownership_players if p.position == "DST" and p.ownership_pct is not None
    }

    def resolve(player: OwnershipPlayer) -> OwnershipPlayer:
        if player.position == "DST":
            pct = pct_by_dst_team.get(player.team)
        else:
            pct = pct_by_name.get(player.player)
        return player.model_copy(update={"ownership_pct": pct}) if pct is not None else player

    return [resolve(player) for player in players]
