"""
DST Trends -- Phase 1 of the person's own "identify players/DSTs/offenses
worth targeting via sack and turnover trends" request (see
backend/services/dst_trends/dst_trends_engine.py for the actual
computation). Two team-level leaderboards, both derived entirely from the
FantasyData_DSTs.csv file already scraped for DK Players/Game Logs -- see
that engine's own docstring for why one file is enough (its own OPP column
already names the opposing offense on every row, so no QB/RB/WR/TE join is
needed to know who a DST's sacks/takeaways were inflicted on).

Phase 2 (not built yet) is expected to cross-reference these against the
current week's own Schedule, so a hot DST only surfaces when it's actually
paired against a leaky offense THIS week -- these two independent
leaderboards are the input that future join would work from.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DstTrendTeamRow(BaseModel):
    team: str
    # How many of the window's weeks this team actually has a DST stat
    # line for (bye weeks, or weeks before this DST/offense's own first
    # game of the season, don't count) -- the denominator for
    # `sacks_per_game`/`takeaways_per_game`, and worth showing so a
    # 1-game "leaderboard-topping" outlier isn't mistaken for a real trend.
    games: int
    # Forcing rows: this DST's own sacks recorded (DEF_SCK) across the
    # window. Allowing rows: the SAME field, but summed from every OTHER
    # team's DST row that had this team as its own OPP that week -- i.e.
    # sacks inflicted ON this team's offensive line, not by it. Same dual
    # meaning as every other field below -- see DstTrendsResult's own
    # forcing/allowing split for which is which.
    sacks: int
    sacks_per_game: float
    # DEF_INT + FR (fumble recoveries) -- forcing: takeaways this DST
    # generated; allowing: turnovers this team's offense gave up.
    takeaways: int
    takeaways_per_game: float


class DstTrendsResult(BaseModel):
    season: int
    # The week actually selected in the app's header -- kept for
    # reference even though the leaderboards themselves cover
    # `through_week` and the `window_weeks` before it.
    week: int
    # `week - 1` -- same "always review the most recently completed week,
    # never the upcoming one" convention as Multipliers' own base_week,
    # since a week still in progress has incomplete DST stats.
    through_week: int
    window_weeks: int
    # DSTs generating sacks/takeaways, ranked by sacks_per_game (ties
    # broken by total sacks) descending -- "who's been getting after the
    # QB and creating turnovers lately."
    forcing: list[DstTrendTeamRow] = Field(default_factory=list)
    # Offenses ALLOWING sacks/turnovers, ranked the same way -- "whose
    # offensive line/QB has been bleeding sacks and giving the ball away
    # lately," i.e. the matchup side of this: a hot DST (top of `forcing`)
    # facing a team near the top of `allowing` this week is the exact
    # "Team A because they've been sacking the QB and the opponent has
    # been giving up sacks" read the person originally asked for.
    allowing: list[DstTrendTeamRow] = Field(default_factory=list)
