"""
Contest Results -- parses a DraftKings contest standings export (the raw
CSV a contest's own "Export to CSV" button produces) into two things:

1. TopLineup -- one contest entry's 9-player lineup, joined against the
   week's DK salary file for Salary/true Position, and against the same
   export's own player-reference table for %Drafted/actual FPTS (see
   backend/services/contest_results/contest_standings_parser.py for the
   raw file's column layout). Exp Pts is a fixed salary * 4 / 1000 -- see
   backend/services/contest_results/contest_results_engine.py's
   EXP_PTS_MULTIPLIER for why this is its own fixed constant rather than
   Settings' Salary Multiplier field (the one Player Rankings/Salary
   Blocks read, which is user-overridable and not scoped to a specific
   past contest the way this feature is). Each LineupPlayer also carries
   its own ownership_rank/points_rank/boom_bust, and the lineup as a whole
   carries a `summary` (LineupSummary) of its own construction -- FLEX's
   true position, game stacks (onslaught/overstack), DST/QB correlation,
   and salary cap usage. See _build_lineup_summary in
   contest_results_engine.py for how each of those is derived.

2. ContestResultRow -- the export's own player-reference table, collapsed
   to one row per PLAYER (not per player+roster-slot combination the raw
   export itself uses) -- see contest_results_engine.py's
   build_contest_result_rows for why: DK's own export tracks %Drafted
   separately per roster slot (e.g. a flex-eligible RB shows up as two
   separate reference rows, one for RB and one for FLEX, each with its
   own smaller %Drafted), which reads as confusing/wrong when shown
   as-is -- a person looking at "Jahmyr Gibbs -- 3.88%" has no way to
   know that's only his FLEX-slot usage, not his real total. Every
   matching row's %Drafted is summed into one true per-player ownership
   figure instead. `position` is the player's own true position from the
   DK salary file (QB/RB/WR/TE/DST), not a roster slot -- FLEX never
   appears here since it was never a real position to begin with, just a
   slot label. Reformatted with Salary also joined in from the DK salary
   file and this week's number attached -- matches the person's own
   dk_{contest}_contest_results_week{week}.csv naming, though `contest`
   itself is a frontend-only label (see backend/api/contest_results/
   player_results.py's docstring) never sent to or stored by this API.

`players` in TopLineup is in the export's own fixed slot order (DST,
FLEX, QB, RB, RB, TE, WR, WR, WR) -- see
contest_standings_parser.parse_lineup_text.

3. OptimalLineup -- not a real contest entry at all, but the single
   highest-actual-FPTS DK Classic lineup (1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX,
   1 DST) that COULD have been built under a given salary cap, built from
   this week's own ContestResultRow list -- "if you'd known the real
   scores in advance, what's the best possible lineup." See
   backend/services/contest_results/optimal_lineup.py's own docstring for
   how it's solved and its player-pool coverage caveat.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LineupPlayer(BaseModel):
    roster_position: str
    player: str
    # None when this player's name didn't match anything in the week's DK
    # salary file (a name mismatch between the two DK exports, or some
    # other edge case) -- see contest_results_engine.py's
    # build_top_lineups. A lineup with any field None here is inherently
    # incomplete; the lineup's own totals below only sum what's real.
    salary: int | None
    position: str | None
    # Summed across every roster slot this player was used in anywhere in
    # the contest (via _total_pct_drafted_by_player), not just the one
    # slot THIS lineup happened to draft them at -- same number
    # ContestResultRow.pct_drafted shows for this player in the Contest
    # Results tab, so the two views never disagree. None only if this
    # player has no reference-table row at all.
    pct_drafted: float | None
    exp_pts: float | None
    act_pts: float | None
    diff: float | None
    # This player's 1-indexed rank among every rostered player at their own
    # true `position` (aggregated by player -- summing %Drafted across
    # every roster slot they were used in, since the same real person's
    # ownership shouldn't be split up just because some entries drafted
    # them at RB and others at FLEX) -- 1 means the single most-owned
    # player at that position in the whole contest. None if `position`
    # itself is unknown (no salary-file match) -- see
    # contest_results_engine.py's _build_player_rank_lookup.
    ownership_rank: int | None
    # Same idea as ownership_rank, but ranked by actual FPTS instead of
    # %Drafted -- 1 means the single highest-scoring player at that
    # position in the whole contest.
    points_rank: int | None
    # "boom"/"bust" when this player's Diff (Act Pts - Exp Pts) crosses
    # +/- contest_results_engine.py's BOOM_BUST_THRESHOLD -- None
    # otherwise (including whenever `diff` itself is None).
    boom_bust: Literal["boom", "bust"] | None


class LineupGameStack(BaseModel):
    """One NFL game this lineup drew 2+ non-DST players from (QB/RB/WR/TE
    only -- DST's own team correlation is its own, separate concept, see
    TopLineup.dst_team/dst_teammates below). "onslaught" mirrors Salary
    Blocks' own Onslaught feature (backend/services/ownership/
    game_blocks.py) -- players from BOTH teams in the game, split into
    `primary` (the larger side) and `bringback` (the smaller side), same
    tie-break-alphabetically-by-team convention as that module's
    _to_game_block. "overstack" is this feature's own term for the
    simpler case Onslaught doesn't cover: 2+ players from ONE team in a
    game, with no bring-back from the other side at all -- bringback_team/
    bringback_positions are None/empty in that case."""

    kind: Literal["onslaught", "overstack"]
    primary_team: str
    primary_positions: list[str]
    bringback_team: str | None
    bringback_positions: list[str]


class LineupSummary(BaseModel):
    """Derived, human-readable-ready signals about one TopLineup's
    construction -- see contest_results_engine.py's _build_lineup_summary
    for how each field is computed. Total lineup ownership isn't
    duplicated here -- it's already TopLineup.total_pct_drafted."""

    # The true position (RB/WR/TE) occupying the FLEX slot -- None if
    # FLEX wasn't in this lineup at all or didn't match the salary file.
    flex_position: str | None
    game_stacks: list[LineupGameStack]
    # The DST's own team, and any OTHER lineup player who shares it --
    # rostering your DST alongside its own offense (as opposed to betting
    # against an opposing offense) is an unusual, worth-flagging build.
    dst_team: str | None
    dst_teammates: list[str]
    # The DST's OPPONENT that week, and the true positions (one entry per
    # matching lineup player, duplicates included) of any lineup players
    # who play for that opponent -- rostering your DST against an offense
    # you're also betting on to score is the more common, worth-flagging
    # correlation (the opposite of dst_teammates above).
    dst_opponent_team: str | None
    dst_opponent_positions: list[str]
    qb_player: str | None
    # True if the QB has a same-team pass-catcher/RB rostered alongside
    # them (a "stack"), False if the QB was played "naked" (no teammate at
    # all), None if there's no QB match to evaluate in the first place.
    qb_stacked: bool | None
    distinct_games: int
    distinct_teams: int
    # $50,000 (DK Classic's cap) minus this lineup's total_salary -- None
    # if any player's salary is unknown, since total_salary would then be
    # an undercount rather than the lineup's real cap usage.
    salary_leftover: int | None


class TopLineup(BaseModel):
    rank: int
    entry_name: str
    # This entry's own reported total, straight from the contest export
    # (not re-derived) -- players' own act_pts should sum to this when
    # every player matched cleanly; see build_top_lineups for why an
    # unmatched player can make total_act_pts diverge from this value.
    points: float
    players: list[LineupPlayer]
    total_salary: int
    total_pct_drafted: float
    total_exp_pts: float
    total_act_pts: float
    total_diff: float
    summary: LineupSummary


class OptimalLineupPlayer(BaseModel):
    """One slot in an OptimalLineup -- unlike LineupPlayer above, every
    field here is a plain non-optional value, since a player only gets
    into an OptimalLineup in the first place if they had a real salary
    and true position to build the roster with (see
    optimal_lineup.py's own docstring)."""

    roster_position: str
    player: str
    position: str
    salary: int
    fpts: float


class OptimalLineup(BaseModel):
    """The single highest actual-FPTS lineup buildable under a salary cap
    from one week's ContestResultRow list -- see backend/services/
    contest_results/optimal_lineup.py's build_optimal_lineup for exactly
    how this is solved (an exact search, not a heuristic) and its own
    important coverage caveat (only players someone actually rostered in
    the contest are eligible, since that's the only pool with a real
    actual-FPTS number to optimize against)."""

    players: list[OptimalLineupPlayer]
    total_salary: int
    total_fpts: float
    # salary_cap minus total_salary -- always >= 0, since a lineup that
    # couldn't fit under the cap is never returned in the first place.
    salary_leftover: int


class ContestResultRow(BaseModel):
    week: int
    player: str
    salary: int | None
    # This player's own true position (QB/RB/WR/TE/DST) from the DK salary
    # file -- None if their name didn't match anything there. Never "FLEX"
    # -- see this module's own docstring for why a roster slot isn't what
    # this field means anymore.
    position: str | None
    # Summed across every roster slot this player was used in anywhere in
    # the contest -- see build_contest_result_rows.
    pct_drafted: float
    fpts: float
