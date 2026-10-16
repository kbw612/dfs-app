"""
Game Logs Summary tab -- slate-wide roll-ups built from the same per-week
stat lines the Game Logs tab reads. Today that is the QB passing-yards panel
(see backend/services/game_logs_summary/qb_passing.py).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# QB passing-yards panel (see backend/services/game_logs_summary/
# qb_passing.py for exactly what is counted). One of a QB's
# own games in the window that cleared a passing-yards bar.
class QbPassingGame(BaseModel):
    week: int
    # The defense he faced, and whether HIS team was at home (vs) or away
    # (@) -- None when the Schedule file has no row for that team/week.
    opponent: str
    is_home: bool | None = None
    pass_yds: int


# One game where a defense allowed 265+ passing yards to a single QB.
class QbPassingAllowedGame(BaseModel):
    week: int
    passer: str
    passer_team: str
    # True when the DEFENSE was at home that week (rendered "vs {passer_team}"),
    # False when it was away ("@ {passer_team}"), None when unknown.
    defense_is_home: bool | None = None
    pass_yds: int


class QbPassingRow(BaseModel):
    name: str
    team: str
    # Depth-chart injury status code (Q/D/O/IR...) when one is set, else None.
    status: str | None = None
    # This week's opponent (the defense he faces).
    opponent: str
    # His own 300+ games, and his 265-299 games (300+ games are NOT repeated
    # in the second list), oldest week first.
    over_300: list[QbPassingGame] = Field(default_factory=list)
    range_265_299: list[QbPassingGame] = Field(default_factory=list)
    # Every 265+ game (300+ included) that opponent's defense allowed in the
    # window, oldest week first.
    opponent_allowed: list[QbPassingAllowedGame] = Field(default_factory=list)


class QbPassingSetup(BaseModel):
    name: str
    opponent: str
    allowed_count: int


class QbPassingSummary(BaseModel):
    # First and last week counted (window is week - window_weeks .. week - 1,
    # clipped to weeks that have data).
    first_week: int
    through_week: int
    # Slate-wide totals (QBs and defenses on the contest's slate). The
    # 265-299 counts exclude the 300+ games.
    qb_games_300: int
    qb_games_265_299: int
    defense_allowed_300: int
    defense_allowed_265_299: int
    # QBs playing this week whose opponent allowed >= 2 games of 265+, most
    # allowed first.
    best_setups: list[QbPassingSetup] = Field(default_factory=list)
    rows: list[QbPassingRow] = Field(default_factory=list)


class GameLogsSummaryResult(BaseModel):
    season: int
    week: int
    window_weeks: int
    # None when there are no QB stat lines in the window at all.
    qb_passing: QbPassingSummary | None = None
