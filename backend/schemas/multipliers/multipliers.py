"""
Multipliers -- a compact "how did last week's pricing actually work out"
review, one row per player currently on the selected Contest's own DK
salary slate: last week's own FPTS/Non_TD_FPTS/TD_FPTS/Multiplier line,
plus that same player's Multiplier from each of the several weeks before
that, pivoted into extra columns on the same row rather than extra rows
(unlike Game Logs, which repeats one row per played week). See
backend/services/multipliers/multipliers_engine.py for how every field
here is derived -- this module is just the response shapes.

Modeled on the person's own "Week N Multipliers" Google Sheets tabs (one
per week, e.g. "Week 13 Multipliers"), which always showed the most
recently completed week's own box score plus five prior weeks' Multiplier
values as reference columns -- this tab generalizes that to any current
week/trailing-count rather than a new hand-built sheet tab every week.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.schemas.game_logs.game_logs import GameOption


class TrailingMultiplier(BaseModel):
    # The historical week this Multiplier is from (e.g. 12, 11, 10, 9, 8
    # for a base week of 13) -- not itself displayed as a value, just the
    # column label ("Multiplier / W12", etc.).
    week: int
    # None when this player has no DK Players tracker row for `week` at
    # all (bye, not yet rostered, tracker not backfilled that far) --
    # same "no data" convention as every other optional numeric field in
    # this app, rendered as "-" rather than a misleading 0.
    multiplier: float | None
    # Same formula as `multiplier` but against non_td_fpts instead of
    # fpts -- lets the frontend's Breakout Watch panel track a player's
    # volume-driven (TD-variance-excluded) value trend across weeks
    # without needing this row's own salary to recompute it client-side.
    # None under the same conditions as `multiplier` (no tracker row that
    # week, or a 0 salary).
    non_td_multiplier: float | None
    # This week's own TD_FPTS -- None only when there's no tracker row for
    # this week at all (same "no data" convention as multiplier/
    # non_td_multiplier above). Lets the frontend's Breakout Watch panel
    # apply its "a week with a touchdown doesn't count as high" rule to
    # trailing weeks too, not just the base week (see MultiplierRow.td_fpts
    # for the base week's own equivalent field).
    td_fpts: float | None


class MultiplierRow(BaseModel):
    name: str
    position: str
    team: str
    # Always the base week (see MultipliersResult.base_week) -- kept on
    # the row itself (rather than only on the result) so the frontend's
    # own generic per-column sort can treat it like any other field.
    week: int
    salary: int
    # None when the Schedule file has no row for this team/week (not
    # uploaded yet, or a team-code mismatch) -- same convention as
    # GameLogRow's own opponent/game_location.
    opponent: str | None
    game_location: Literal["Home", "Away", "BYE"] | None
    multiplier: float | None
    # Same "fpts/(salary/1000)" formula as `multiplier`, but against
    # non_td_fpts -- the base week's own value-per-dollar with touchdown
    # variance stripped out (see TrailingMultiplier.non_td_multiplier's
    # own docstring for why this exists). None only when salary is 0.
    non_td_multiplier: float | None
    fpts: float
    non_td_fpts: float
    non_td_fpts_pct: float | None
    td_fpts: float
    td_fpts_pct: float | None
    # Exactly `trailing_weeks` entries (see MultipliersResult), ordered
    # most-recent-first (base_week - 1, base_week - 2, ...) -- matches the
    # left-to-right "Multiplier / W12, W11, W10, ..." column order the
    # person's own Sheet used.
    trailing: list[TrailingMultiplier]


class MultipliersResult(BaseModel):
    season: int
    # The week actually selected in the app's header (e.g. 14) -- kept
    # for reference even though every row's own `week` field is
    # `base_week`, not this.
    week: int
    # `week - 1` -- every row's own FPTS/Multiplier/etc. is this week's
    # data, not `week` itself (see multipliers_engine.py's own docstring
    # for why this tab is always "last week's review", not "this week").
    base_week: int
    trailing_weeks: int
    games: list[GameOption]
    rows: list[MultiplierRow]
