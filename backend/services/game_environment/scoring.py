"""
Game Environment scoring: turns a team's implied total (plus the game's
over/under, for one edge case) into the 1/2/3 tiered score Player
Pool (and potentially other tabs later) uses, per the rule as described:

    3 points: team total >=24, OR team total >=22 with the
              game's over/under >=47
    2 points: team total 20-23.75
    1 point:  team total <=19 ("19 or less")

This is on the same 1.0-3.0 scale as every other Player Pool score field
(see backend/schemas/player_pool/player_pool.py) -- Game Environment used
to live on its own 0.0-1.0 scale (0/0.5/1) so it carried half the weight
of the other fields, but that asymmetry was a deliberate early design
choice, not a technical constraint, and was later reversed so every field
weighs the same in a player's Total (see engine.py's
_DEFAULT_GAME_ENVIRONMENT). The three tiers here are exactly the old
0/0.5/1 bands remapped via score = old_score * 2 + 1.

The three described bands (>=24, 20-23.75, <=19) leave two narrow gaps
(19-20, 23.75-24) unaddressed by the letter of the rule -- rather than
leaving those unscored, this resolves them the way the *intent* of the
three bands clearly reads: anything from 20 up to (but not qualifying
for) the top band is still the middle tier, and anything below 20 is the
bottom tier. So the effective thresholds are: >=24 (or >=22 with a 47+
over/under) => 3.0; >=20 => 2.0; otherwise => 1.0. This score is always a
suggestion a person can override (see engine.py) -- these boundaries
existing at all doesn't stop a value from being hand-adjusted.
"""

from __future__ import annotations

from typing import Optional

from backend.schemas.game_environment.game_environment import GameEnvironmentEntry


def team_implied_total(entry: GameEnvironmentEntry, team: str) -> Optional[float]:
    """Whichever of entry's two implied totals belongs to `team` -- None
    if `team` is neither side of this game (shouldn't happen if the
    caller matched the entry by this player's own game_key, but defensive
    against a mismatch rather than guessing)."""
    if team == entry.home_team:
        return entry.home_implied_total
    if team == entry.away_team:
        return entry.away_implied_total
    return None


def score_game_environment(team_total: Optional[float], over_under: Optional[float]) -> Optional[float]:
    """None if there's no team total to score at all (odds not entered
    yet for this game) -- otherwise always resolves to 1.0/2.0/3.0, see
    this module's docstring for the exact bands."""
    if team_total is None:
        return None
    if team_total >= 24 or (team_total >= 22 and over_under is not None and over_under >= 47):
        return 3.0
    if team_total >= 20:
        return 2.0
    return 1.0
