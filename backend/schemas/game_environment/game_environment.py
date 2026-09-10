"""
Game Environment: the weekly Vegas-line data (each team's projected/
implied total and the game's over/under) that several tabs can draw on --
today Player Pool's Game Environment score (see backend/services/
game_environment/scoring.py) and Game Matchup context, but deliberately
not owned by that tab's own storage, since the same numbers are useful
anywhere a game's expected pace/scoring matters.

One entry per (season, week, game) -- entered once per matchup, not
duplicated per player, since these are properties of the game itself.

No spread field -- oneweekseason.com's scraped source (backend/services/
vegas_lines/scraper.py) publishes implied totals and over/under
directly, not the raw spread, and nothing in scoring has ever consumed a
spread value, so there was nothing for a spread field to do.
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
    over_under: Optional[float] = None
    home_implied_total: Optional[float] = None
    away_implied_total: Optional[float] = None
