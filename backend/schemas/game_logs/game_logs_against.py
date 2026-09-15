"""
Game Logs Against -- the inverse of Game Logs: instead of one team's own
roster's scoring history, this shows how OPPOSING players performed in
their own recent games against a given team, one "Against {team}" panel
per team in the current week's slate. See backend/services/game_logs/
game_logs_against_engine.py for how every field here is derived -- this
module is just the response shapes.

No Touches/Targets/Receptions/etc. here (unlike GameLogRow) -- the
person's own reference spreadsheet/script for this tab never carried
those columns, only Week/Name/Position/Salary/GameLoc/Multiplier/FPTS/
Non_TD_FPTS/TD_FPTS(_%), so this tab needs the DK Players tracker and the
Schedule file only, not the FantasyData weekly stats files Game Logs
itself also reads.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.schemas.game_logs.game_logs import GameOption


class GameLogAgainstRow(BaseModel):
    # Which team's "Against" panel this row belongs to -- not itself a
    # displayed column (the panel heading already says "Against {team}"),
    # but needed so the frontend can group/filter without re-deriving it.
    against_team: str
    week: int
    name: str
    position: str
    salary: int
    # The opposing player's own home/away for that week's game (which,
    # since it's a game against `against_team`, doubles as `against_team`'s
    # own game location too, just from the other side) -- None when the
    # Schedule file has no row for it.
    game_location: Literal["Home", "Away", "BYE"] | None
    multiplier: float | None
    fpts: float
    non_td_fpts: float
    non_td_fpts_pct: float | None
    td_fpts: float
    td_fpts_pct: float | None


class GameLogsAgainstResult(BaseModel):
    season: int
    week: int
    lookback_weeks: int
    games: list[GameOption]
    rows: list[GameLogAgainstRow]
