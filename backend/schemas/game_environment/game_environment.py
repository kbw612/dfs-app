"""
Game Environment: the weekly Vegas-line data (point spread, each team's
projected/implied total, and the game's over/under) that several tabs can
draw on -- today Player Pool's Game Environment score (see
backend/services/game_environment/scoring.py) and Game Matchup context,
but deliberately not owned by that tab's own storage, since the same
numbers are useful anywhere a game's expected pace/scoring matters.

One entry per (season, week, game) -- entered once per matchup, not
duplicated per player, since these are properties of the game itself.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class GameEnvironmentEntry(BaseModel):
    season: int
    week: int
    # "AWAY-HOME" (alphabetically sorted team abbreviations), same
    # convention as ownership/position_blocks.py's game_key/game_label.
    game_key: str
    home_team: str
    away_team: str
    # The home team's line -- negative means the home team is favored,
    # positive means they're the underdog (standard sportsbook
    # convention, e.g. -3.5 means the home team is favored by 3.5). The
    # away team's spread is just the negation of this, so only one field
    # is stored. Reference/context only today -- no scoring formula
    # consumes this yet (see the Game Matchup rule's open item).
    home_spread: Optional[float] = None
    over_under: Optional[float] = None
    home_implied_total: Optional[float] = None
    away_implied_total: Optional[float] = None
