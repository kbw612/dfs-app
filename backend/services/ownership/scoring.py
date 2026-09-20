"""
Ownership% -> Player Pool score, the same 1.0-3.0 scale every other score
field uses (see backend/services/game_environment/scoring.py for the
analogous Game Environment formula). Offense and DST use the same
*low*-ownership-earns-the-*top*-score direction (a less-owned player is
the more attractive differentiation play) but different breakpoints, so
each gets its own function.

Offense (score_ownership_pct) -- bands match the Ownership popover exactly
(frontend/src/components/scoringNotes.ts's OWNERSHIP_NOTES):

    < 10%            -> 3.0
    10% - 20%         -> 2.0
    > 20%            -> 1.0

DST (score_dst_ownership_pct) -- bands match DST_OWNERSHIP_NOTES, using
tighter breakpoints than offense since DST ownership tends to concentrate
on far fewer options each week:

    <= 2%            -> 3.0
    2% - 9.99%        -> 2.0
    >= 10%           -> 1.0

Both used by backend/api/player_pool/calculate_ownership_scores.py, the
Player Rankings tab's Ownership refresh icon -- mirrors Vegas Lines' own
refresh for Game Environment (backend/api/vegas_lines/apply.py), just
computing a score directly from this week's Ownership projections instead
of writing intermediate reference data for a separate formula to read
later.
"""

from __future__ import annotations


def score_ownership_pct(ownership_pct: float | None) -> float | None:
    """None when there's nothing to score off of yet -- this player
    wasn't in the current Ownership projections upload (see
    backend/services/player_pool/enrichment.py's ownership_retrieved vs.
    per-player ownership_pct distinction). Callers should leave that
    player's saved Ownership score untouched rather than treating a
    missing projection as "0% owned, score 3.0" -- see
    calculate_ownership_scores_endpoint's skipped_count."""
    if ownership_pct is None:
        return None
    if ownership_pct < 10:
        return 3.0
    if ownership_pct <= 20:
        return 2.0
    return 1.0


def score_dst_ownership_pct(ownership_pct: float | None) -> float | None:
    """DST's own Ownership breakpoints -- see this module's docstring for
    why these differ from score_ownership_pct's offense bands. Same
    None-passthrough contract: a DST with no ownership_pct yet is left
    unscored rather than defaulting to a specific band."""
    if ownership_pct is None:
        return None
    if ownership_pct <= 2:
        return 3.0
    if ownership_pct < 10:
        return 2.0
    return 1.0
