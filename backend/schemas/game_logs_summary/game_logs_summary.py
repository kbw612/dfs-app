"""
Game Logs Summary tab -- slate-wide roll-ups built from the same per-week
stat lines the Game Logs tab reads. Today that is the QB passing-yards panel
(see backend/services/game_logs_summary/qb_passing.py).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.schemas.game_logs.game_logs import GameOption


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


# One of a QB's own games with 3+ passing TDs.
class QbTdGame(BaseModel):
    week: int
    opponent: str
    is_home: bool | None = None
    pass_td: int


# One game where a defense allowed 3+ passing TDs to a single QB.
class QbAllowedTdGame(BaseModel):
    week: int
    passer: str
    passer_team: str
    defense_is_home: bool | None = None
    pass_td: int


class QbPassingRow(BaseModel):
    name: str
    team: str
    # Depth-chart injury status code (Q/D/O/IR...) when one is set, else None.
    status: str | None = None
    # This week's salary from the contest salary file; None when unknown.
    salary: int | None = None
    # This week's opponent (the defense he faces).
    opponent: str
    # His own 300+ games, and his 265-299 games (300+ games are NOT repeated
    # in the second list), oldest week first.
    over_300: list[QbPassingGame] = Field(default_factory=list)
    range_265_299: list[QbPassingGame] = Field(default_factory=list)
    # Every 265+ game (300+ included) that opponent's defense allowed in the
    # window, oldest week first.
    opponent_allowed: list[QbPassingAllowedGame] = Field(default_factory=list)
    # His own 3+ passing-TD games, and the 3+ TD games the opponent allowed.
    td_games: list[QbTdGame] = Field(default_factory=list)
    opponent_allowed_td: list[QbAllowedTdGame] = Field(default_factory=list)


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
    # Games of 3+ passing TDs by slate QBs / allowed by slate defenses.
    qb_games_td3: int = 0
    defense_allowed_td3: int = 0
    # QBs playing this week whose opponent allowed >= 2 games of 265+, most
    # allowed first.
    best_setups: list[QbPassingSetup] = Field(default_factory=list)
    rows: list[QbPassingRow] = Field(default_factory=list)


# -- RB rushing panel (see backend/services/game_logs_summary/rb_rushing.py) --


class RbRushingGame(BaseModel):
    """One of a RB's own games in the window that cleared a rushing bar."""

    week: int
    opponent: str
    # True when the RB's team was at home ("vs"), False when away ("@").
    is_home: bool | None = None
    rush_yds: int


class RbRusher(BaseModel):
    name: str
    team: str
    rush_yds: int


class RbRushingAllowedGame(BaseModel):
    """One game where a defense allowed 75+ COMBINED rushing yards to an
    offense's running backs. `total_yds` is the sum across every RB that
    team used; `rushers` lists each RB's own yards, most first."""

    week: int
    # The offense's team (rendered "vs {team}" / "@ {team}" from the
    # defense's side, same convention as the QB panel).
    team: str
    defense_is_home: bool | None = None
    total_yds: int
    rushers: list[RbRusher] = Field(default_factory=list)


class RbTdGame(BaseModel):
    """One of a RB's own games with 1+ touchdowns (rushing or receiving,
    depending on the panel it sits in)."""

    week: int
    opponent: str
    is_home: bool | None = None
    td: int


class RbTdScorer(BaseModel):
    name: str
    team: str
    td: int


class RbAllowedTdGame(BaseModel):
    """One game where a defense allowed 1+ touchdowns of the panel's type to
    an offense's running backs COMBINED. `scorers` lists each RB who scored,
    most TDs first."""

    week: int
    team: str
    defense_is_home: bool | None = None
    total_td: int
    scorers: list[RbTdScorer] = Field(default_factory=list)


class RbRushingRow(BaseModel):
    name: str
    team: str
    status: str | None = None
    # This week's salary from the contest salary file; None when unknown.
    salary: int | None = None
    opponent: str
    # His own 100+ games, and his 75-99 games (100+ not repeated), oldest first.
    over_100: list[RbRushingGame] = Field(default_factory=list)
    range_75_99: list[RbRushingGame] = Field(default_factory=list)
    # Every game (100+ combined included) the opponent allowed 75+ combined
    # RB rushing yards, oldest first.
    opponent_allowed: list[RbRushingAllowedGame] = Field(default_factory=list)
    # His own 1+ rushing-TD games, and the games the opponent allowed 1+
    # rushing TDs to a team's RBs combined.
    td_games: list[RbTdGame] = Field(default_factory=list)
    opponent_allowed_td: list[RbAllowedTdGame] = Field(default_factory=list)


class RbRushingSetup(BaseModel):
    name: str
    opponent: str
    allowed_count: int


class RbRushingSummary(BaseModel):
    first_week: int
    through_week: int
    # Per-RB games on slate teams (a RB counts once per game).
    rb_games_100: int
    rb_games_75_99: int
    # Team-games on slate defenses where the offense's RBs COMBINED for the
    # bucket (75-99 excludes the 100+ games).
    defense_allowed_100: int
    defense_allowed_75_99: int
    # Per-RB rushing-TD games, and team-games where a slate defense allowed
    # 1+ rushing TD to the offense's RBs combined.
    rb_games_td: int = 0
    defense_allowed_td: int = 0
    best_setups: list[RbRushingSetup] = Field(default_factory=list)
    rows: list[RbRushingRow] = Field(default_factory=list)


# -- RB receiving panel (see backend/services/game_logs_summary/rb_receiving.py) --


class RbReceivingGame(BaseModel):
    """One of a RB's own games with 50+ receiving yards."""

    week: int
    opponent: str
    is_home: bool | None = None
    rec_yds: int


class RbReceiver(BaseModel):
    name: str
    team: str
    rec_yds: int


class RbReceivingAllowedGame(BaseModel):
    """One game where a defense allowed 50+ COMBINED receiving yards to an
    offense's running backs; `receivers` lists each RB's own yards."""

    week: int
    team: str
    defense_is_home: bool | None = None
    total_yds: int
    receivers: list[RbReceiver] = Field(default_factory=list)


class RbReceivingRow(BaseModel):
    name: str
    team: str
    status: str | None = None
    # This week's salary from the contest salary file; None when unknown.
    salary: int | None = None
    opponent: str
    # His own 50+ receiving-yard games, oldest first.
    games_50: list[RbReceivingGame] = Field(default_factory=list)
    # Games the opponent allowed 50+ combined RB receiving yards.
    opponent_allowed: list[RbReceivingAllowedGame] = Field(default_factory=list)
    # His own 1+ receiving-TD games, and the games the opponent allowed 1+
    # receiving TDs to a team's RBs combined.
    td_games: list[RbTdGame] = Field(default_factory=list)
    opponent_allowed_td: list[RbAllowedTdGame] = Field(default_factory=list)


class RbReceivingSummary(BaseModel):
    first_week: int
    through_week: int
    rb_games_50: int
    defense_allowed_50: int
    rb_games_td: int = 0
    defense_allowed_td: int = 0
    best_setups: list[RbRushingSetup] = Field(default_factory=list)
    rows: list[RbReceivingRow] = Field(default_factory=list)


# -- Salary-multiplier panels, one per QB/RB/WR/TE (see backend/services/game_logs_summary/position_multipliers.py) --


class PositionMultiplierGame(BaseModel):
    """One of a player's own games that cleared a multiplier bar. `multiplier` is
    FPTS / (salary / 1000) for the 3x+ buckets and non-TD FPTS / (salary /
    1000) for the non-TD column."""

    week: int
    opponent: str
    is_home: bool | None = None
    multiplier: float
    # That week's DK salary.
    salary: int = 0


class PositionMultiplierAllowedGame(BaseModel):
    """One player game a defense allowed in a bucket (one line per player
    game, not combined across a team's players)."""

    week: int
    player: str
    player_team: str
    # True when the DEFENSE was at home ("vs {player_team}"), False when away.
    defense_is_home: bool | None = None
    multiplier: float
    # That week's DK salary for the player.
    salary: int = 0


class PositionMultiplierRow(BaseModel):
    name: str
    team: str
    status: str | None = None
    # This week's salary from the contest salary file; None when unknown.
    salary: int | None = None
    opponent: str
    # His own 4x+ games and 3-3.99x games (no overlap), oldest first.
    over_4x: list[PositionMultiplierGame] = Field(default_factory=list)
    range_3x_399: list[PositionMultiplierGame] = Field(default_factory=list)
    # His own games with a non-TD multiplier of 2.5x+ that are NOT in the two
    # lists above (total multiplier under 3x).
    non_td_2_5x: list[PositionMultiplierGame] = Field(default_factory=list)
    # Opponent's allowed games at this position: 3x+ (4x+ included), then non-TD 2.5x+ (excluding games already in the 3x+ list).
    opponent_allowed: list[PositionMultiplierAllowedGame] = Field(default_factory=list)
    opponent_allowed_non_td: list[PositionMultiplierAllowedGame] = Field(default_factory=list)


class PositionMultiplierSummary(BaseModel):
    first_week: int
    through_week: int
    # QB, RB, WR or TE -- which position this panel covers.
    position: str
    # Player games on slate teams / allowed by slate defenses (each player
    # game is one count; 3x_399 excludes the 4x+ games).
    player_games_4x: int
    player_games_3x_399: int
    player_games_non_td_2_5x: int
    defense_allowed_4x: int
    defense_allowed_3x_399: int
    defense_allowed_non_td_2_5x: int
    best_setups: list[RbRushingSetup] = Field(default_factory=list)
    rows: list[PositionMultiplierRow] = Field(default_factory=list)


class GameLogsSummaryResult(BaseModel):
    season: int
    week: int
    window_weeks: int
    # This week's games on the contest's slate -- feeds the Game / Team chip
    # filters (same shape and source as Game Logs' own `games`).
    games: list[GameOption] = Field(default_factory=list)
    # True when the selected contest has no DK salary file for this week yet,
    # so the slate could not be narrowed and every league game is shown. The
    # frontend uses it to show a "showing all games" notice.
    contest_salary_file_missing: bool = False
    # None when there are no QB stat lines in the window at all.
    qb_passing: QbPassingSummary | None = None
    # None when there are no RB stat lines in the window at all.
    rb_rushing: RbRushingSummary | None = None
    # None when there are no RB stat lines in the window at all.
    rb_receiving: RbReceivingSummary | None = None
    # Salary-multiplier panels, one per position; each None when the DK Players
    # tracker has no priced rows for that position in the window.
    qb_multipliers: PositionMultiplierSummary | None = None
    rb_multipliers: PositionMultiplierSummary | None = None
    wr_multipliers: PositionMultiplierSummary | None = None
    te_multipliers: PositionMultiplierSummary | None = None


# --- FPTS panels (QB, RB, WR, TE, DST) -------------------------------------
# Everything here is finished for display: counts, preformatted lines, group
# sizes. The frontend only renders it.


class FptsLine(BaseModel):
    """One game: its display text, plus muted detail lines under it (QB: pass
    attempts and touchdowns; RB: volume, then production)."""

    text: str
    details: list[str] = Field(default_factory=list)


class FptsCell(BaseModel):
    """One table cell: how many games, and one display line per game."""

    count: int = 0
    lines: list[FptsLine] = Field(default_factory=list)


class FptsRow(BaseModel):
    name: str
    team: str
    status: str | None = None
    # This week's salary from the contest salary file; None when unknown.
    salary: int | None = None
    elite: FptsCell
    strong: FptsCell


class FptsGroup(BaseModel):
    """The players facing one opponent this week, with that opponent's allowed
    games shown once for the whole group."""

    opponent: str
    row_count: int  # number of rows in the group (for the cells that span it)
    allowed_total: int
    allowed_elite: FptsCell
    allowed_strong: FptsCell
    rows: list[FptsRow]


class PositionFptsSummary(BaseModel):
    position: str
    # Heading of the opponent columns: "Opp D" (QB/RB/WR/TE) or "Opp offense" (DST).
    opponent_label: str
    weeks_label: str  # "Weeks 1-6"
    elite_label: str  # "27+"
    strong_label: str  # "22-26.9"
    player_games_elite: int
    player_games_strong: int
    allowed_elite: int
    allowed_strong: int
    best_setups: list[str] = Field(default_factory=list)
    row_count: int
    groups: list[FptsGroup] = Field(default_factory=list)


class FptsPanelsResult(BaseModel):
    qb: PositionFptsSummary | None = None
    rb: PositionFptsSummary | None = None
    wr: PositionFptsSummary | None = None
    te: PositionFptsSummary | None = None
    dst: PositionFptsSummary | None = None
