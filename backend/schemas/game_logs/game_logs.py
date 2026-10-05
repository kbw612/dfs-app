"""
Game Logs -- for every player currently rostered at QB/RB/WR/TE/DST (per
the DK Players tracker's most recent snapshot week), their own recent-weeks
scoring history, enriched with schedule (Opponent/GameLoc), usage
(Touches/Targets/Receptions/Receiving Yards/Rec TD/Rush Att/Rush Yards/
Rush TD, Target Share %/Touch Share %), -- QB only -- their own passing
line (Cmp/Att/Cmp%/Yds/Avg/TD/Int/Sck/Rtg), and -- DST only -- their own
sacks (recorded, not taken -- see this module's own `sacks` field) data.
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
    # These are None (not 0) for a position whose FantasyData file simply
    # doesn't carry that stat -- QB has no targets/receptions/
    # receiving_yards/rec_td columns at all (see weekly_stats_loader.py's
    # _USAGE_STAT_COLUMNS) -- rather than a real 0 for "attempted but
    # caught nothing." rush_td IS present for QB (its file carries
    # RUSHING_TD too, same as RB/WR/TE) -- only rec_td is receiving-only.
    touches: int | None
    targets: int | None
    receptions: int | None
    receiving_yards: int | None
    rec_td: int | None
    rush_att: int | None
    rush_yards: int | None
    rush_td: int | None
    # Read straight off the FantasyData file's own TGT_SHARE/TOUCH_SHARE/
    # OPP_SHARE columns, same as touches/targets/etc. above -- written once
    # per week by the "Calc Week Points" action (see backend/services/shared/
    # usage_shares.py), not recomputed here. None when that week hasn't
    # been calculated yet, or (target_share_pct only) for QB, same "not
    # applicable" reasoning as targets/receptions/receiving_yards above --
    # touch_share_pct and opp_share_pct stay meaningful (carries-only
    # shares) for a QB instead, see usage_shares.py's own docstring.
    target_share_pct: float | None
    touch_share_pct: float | None
    opp_share_pct: float | None
    # QB's own passing line, straight from the FantasyData QB file's own
    # PASSING_* (and INT/SCK/RATING) columns -- always None for every
    # other position, since none of them have a passing line at all (same
    # "not applicable" convention as touches/targets/etc. above, just for
    # the position that has NEITHER of those instead of this).
    pass_cmp: int | None
    pass_att: int | None
    pass_cmp_pct: float | None
    pass_yds: int | None
    pass_avg: float | None
    pass_td: int | None
    pass_int: int | None
    pass_sck: int | None
    pass_rtg: float | None
    # Background-color tier for this one week's raw pass_att/pass_yds
    # value -- "low" if it's at or under that stat's red-shading
    # threshold, "high" if it's at or over its green-shading threshold,
    # None either for a value in between or for pass_att/pass_yds itself
    # being None (not applicable for this position/week). Deliberately NOT
    # added for rush_att/rush_yards/receptions/receiving_yards -- the
    # person's own request colors only the passing columns in this
    # per-week grid (rush/rec already have their own unrelated top-2-share
    # shading, see shareRankClassName in the frontend). Same thresholds as
    # TeamStatSummaryRow's own average_tier/median_tier for these two
    # stats -- see backend/services/game_logs/game_logs_engine.py's
    # tier_for_stat_value, the single shared source of truth for both.
    pass_att_tier: Literal["low", "high"] | None
    pass_yds_tier: Literal["low", "high"] | None
    # DST's own sacks *recorded* -- always None for every other position
    # (same "not applicable" convention as pass_cmp/etc. above for non-QBs).
    # Deliberately its own field rather than reusing pass_sck: that field is
    # sacks *taken* by a QB, a different stat with the opposite meaning --
    # see weekly_stats_scraper.py's _DST_HEADER_MAP comment for why the two
    # are even stored under different CSV column names.
    sacks: int | None


class GameOption(BaseModel):
    key: str
    label: str
    teams: list[str]


class StatAverage(BaseModel):
    """One counting stat's average and median across however many of a
    team's own per-week totals are included in the summary (see
    TeamStatSummaryRow.games) -- both None when every one of that team's
    weeks has this stat's team total as None (nobody on the roster that
    week had a non-None value for it -- e.g. Pass Yds on a week the team's
    QB row wasn't found, or a week FantasyData hasn't been scraped for
    yet), never a silent 0. See backend/services/game_logs/
    game_logs_engine.py's build_team_stat_summary for how these are
    computed.

    average_tier/median_tier are this same stat's background-color tier
    for the average/median value respectively -- "low"/"high" for one of
    the 4 stats with defined red/green thresholds (Pass Att, Pass Yds,
    Rush Att, Rush Yds) once that value crosses one, None otherwise
    (either in between the two thresholds, or a stat with no thresholds
    at all -- Rec TD, Rush TD, Pass TD, or average/median itself being
    None). See game_logs_engine.py's tier_for_stat_value for the single
    shared thresholds table."""

    average: float | None
    median: float | None
    average_tier: Literal["low", "high"] | None
    median_tier: Literal["low", "high"] | None


class TeamStatSummaryRow(BaseModel):
    """One team's own Average/Median over 7 counting stats (Rec TD, Rush
    Att, Rush Yds, Rush TD, Pass Att, Pass Yds, Pass TD) -- a TEAM total,
    not a single player's: for each week, every currently-shown player's
    own value for a stat is summed into that week's team total first, and
    this row's average/median are computed across those per-week team
    totals. Covers exactly the weeks already shown in `rows` above (the
    post-zero-FPTS-filter weeks within the lookback window, per the
    person's own "only the weeks shown" answer) -- not the raw lookback
    window, so this always matches what's visibly on screen. `team` is
    whichever team this row is grouped under -- the roster team itself
    for Game Logs, or the "Against {team}" panel's own team for Game Logs
    Against (see each engine's own call site for which).

    Receptions and Receiving Yards were dropped from this summary at the
    person's own request -- they're still on every per-week GameLogRow/
    GameLogAgainstRow, just not summarized here."""

    team: str
    # How many distinct weeks had at least one row to sum into a team
    # total -- NOT necessarily the full lookback_weeks (a bye week, or
    # every rostered player having a 0-FPTS week hidden, means fewer weeks
    # than the lookback window itself).
    games: int
    rec_td: StatAverage
    rush_att: StatAverage
    rush_yards: StatAverage
    rush_td: StatAverage
    pass_att: StatAverage
    pass_yds: StatAverage
    pass_td: StatAverage


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
    # One entry per distinct team in `rows` -- see TeamStatSummaryRow's own
    # docstring.
    team_stat_summary: list[TeamStatSummaryRow]
