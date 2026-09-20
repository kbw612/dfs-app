"""
Game Logs Against -- the inverse of Game Logs: instead of one team's own
roster's scoring history, this shows how OPPOSING players performed in
their own recent games against a given team, one "Against {team}" panel
per team in the current week's slate. See backend/services/game_logs/
game_logs_against_engine.py for how every field here is derived -- this
module is just the response shapes.

Touches/Targets/Receptions/Receiving Yards/Rush Att/Rush Yards, Target
Share %/Touch Share %, and QB's own passing line are all included too,
mirroring GameLogRow's own fields of the same name -- all read straight
off the same FantasyData weekly stats files Game Logs reads, so this tab
needs them too, not just the DK Players tracker and Schedule file. The
person's own original reference spreadsheet/script for this tab never
carried the usage columns (only Week/Name/Position/Salary/GameLoc/
Multiplier/FPTS/Non_TD_FPTS/TD_FPTS(_%)), but they were added here to
match Game Logs once the same underlying data became available.
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
    # Same fields, read/derived the same way (touches via
    # usage_shares.compute_touches, the rest straight off the FantasyData
    # file's own stat line), same "None (not 0) for a position whose stat
    # file doesn't carry that column at all" convention as GameLogRow's
    # own touches/targets/receptions/receiving_yards/rush_att/rush_yards
    # -- see that schema's docstring.
    touches: int | None
    targets: int | None
    receptions: int | None
    receiving_yards: int | None
    rush_att: int | None
    rush_yards: int | None
    # Same fields, read the same way (straight off the FantasyData file's
    # own stat line), same "not applicable"/"data missing" None
    # conventions, as GameLogRow's own target_share_pct/touch_share_pct/
    # opp_share_pct and passing line -- see that schema's docstring.
    target_share_pct: float | None
    touch_share_pct: float | None
    opp_share_pct: float | None
    pass_cmp: int | None
    pass_att: int | None
    pass_cmp_pct: float | None
    pass_yds: int | None
    pass_avg: float | None
    pass_td: int | None
    pass_int: int | None
    pass_sck: int | None
    pass_rtg: float | None


class GameLogsAgainstResult(BaseModel):
    season: int
    week: int
    lookback_weeks: int
    games: list[GameOption]
    rows: list[GameLogAgainstRow]
