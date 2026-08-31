"""
Player Attributes: a player's Volume/Opportunities and Talent/Explosiveness
scores -- the two Player Pool fields that describe the player themselves
rather than this week's specific matchup/context (contrast Game Matchup,
Ownership, Game Environment, all of which are expected to be re-entered or
re-derived fresh each week). Split out of Player Pool's own storage into
this shared resource for the same reason Game Environment was: a player's
role/talent grade is a fact about them, not about Player Pool specifically,
so other tabs should eventually be able to read (or set) it too.

Each entry is still saved per (season, week, player) -- see
repositories/player_attributes/entries_repo.py -- because the whole point
is to preserve week-history exactly as described in planning: "Gibbs could
be a 3 weeks 1-10, get hurt and out weeks 11-13, starts playing week 14 and
is a 2 until the end of the season -- keep a week history, but the default
value only applies to weeks moving forward; past weeks still retain the
value for that week." That's the same carry-forward-from-the-most-recent-
earlier-week mechanic Player Pool used before this split (see
resolve_carry_forward_value) -- only where it lives has changed, not how it
behaves. "Setting a new default" is just saving a value for the current (or
any future) week; nothing about this schema treats defaults as a separate
concept from a week's entry.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

_Score = Optional[float]


def _score_field() -> _Score:
    return Field(default=None, ge=1.0, le=3.0)


class PlayerAttributeEntry(BaseModel):
    season: int
    week: int
    player: str

    volume: _Score = _score_field()
    talent: _Score = _score_field()
