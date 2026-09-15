"""
Game Logs -- for every player currently rostered at QB/RB/WR/TE (per the
DK Players tracker's most recent snapshot week), their own recent-weeks
scoring history, enriched with schedule (Opponent/GameLoc) and usage
(Touches/Targets/Receptions/Receiving Yards/Rush Att/Rush Yards) data.
See backend/services/game_logs/game_logs_engine.py for how every field
here is derived -- this module is just the response shapes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GameLogRow(BaseModel):
    week: int
    name: str
    position: str
    team: str
    salary: int
    # None when the Schedule file hasn't been uploaded (or has no row for
    # this team/week) -- rendered as "-" by the frontend, same convention
    # as every other missing-side-channel-data case in this app.
    opponent: str | None
    game_location: Literal["Home", "Away", "BYE"] | None
    # FPTS / (Salary / 1000) -- None when Salary is 0 (nothing to divide
    # by), same "not a real player-week" case the frontend already treats
    # as "-" everywhere else a multiplier/rate is shown.
    multiplier: float | None
    fpts: float
    non_td_fpts: float
    non_td_fpts_pct: float | None
    td_fpts: float
    td_fpts_pct: float | None
    # These five are None (not 0) for a position whose FantasyData file
    # simply doesn't carry that stat -- QB has no targets/receptions/
    # receiving_yards column at all (see weekly_stats_loader.py's
    # _USAGE_STAT_COLUMNS) -- rather than a real 0 for "attempted but
    # caught nothing."
    touches: int | None
    targets: int | None
    receptions: int | None
    receiving_yards: int | None
    rush_att: int | None
    rush_yards: int | None


class GameOption(BaseModel):
    key: str
    label: str
    teams: list[str]


class GameLogsResult(BaseModel):
    season: int
    week: int
    # The DK Players tracker week actually used to decide "who's currently
    # rostered" -- equals `week` once that week's players have been added,
    # otherwise the latest earlier week that has rows (see
    # game_logs_engine.py's build_game_log_rows). Surfaced so the frontend
    # can say so if it's not `week` itself.
    reference_week: int
    lookback_weeks: int
    games: list[GameOption]
    rows: list[GameLogRow]
