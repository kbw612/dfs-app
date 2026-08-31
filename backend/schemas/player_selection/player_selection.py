"""
Player Selection: lets Settings narrow down which QB/RB/WR/TE players from
this week's salary file actually show up in Player Pool and Salary Blocks
(see frontend/src/components/PlayerSelectionGrid.tsx). DST is deliberately
untouched by this feature -- every DST from the salary file always passes
through to both tabs, no selection needed (see
backend/services/player_selection/engine.py's filter_selected_players).

`selected` defaults to a computed value based on position + salary (see
engine.py's default_selected) rather than "everyone selected" -- a player
only needs an explicit PlayerSelectionOverride on disk once someone
actually flips a checkbox away from that default. This is scoped to
(season, week, platform), same as the salary file itself -- there's no
carry-forward from an earlier week the way Volume/Talent has; each week's
salary file gets its own fresh selection.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PlayerSelectionRow(BaseModel):
    player: str
    position: str
    team: str
    salary: int
    # Parsed from the salary file's "Game Info" column (see
    # backend/services/dk_salary/dk_salary_parsing.py's parse_game_info) --
    # the opponent's abbreviation plus whether this player is home or away,
    # same shape as OwnershipPlayer.opponent/is_home. The kickoff date/time
    # itself isn't tracked anywhere in this app (see that module's
    # docstring), so there's nothing more to show here than the matchup.
    opponent: str
    is_home: Optional[bool] = None
    selected: bool


class PlayerSelectionResult(BaseModel):
    players: list[PlayerSelectionRow]


class PlayerSelectionOverride(BaseModel):
    season: int
    week: int
    platform: str
    player: str
    selected: bool
