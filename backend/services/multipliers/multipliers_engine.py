"""
Computes the Multipliers tab's rows -- for every QB/RB/WR/TE/DST on the
currently-selected Contest's own DK salary slate, last week's own FPTS/
Non_TD_FPTS/TD_FPTS/Multiplier line (the "base week" -- always `week - 1`,
since this tab exists to review how last week's real pricing worked out
before setting this week's lineup, not to preview the upcoming week),
plus that same player's own Multiplier from each of the `trailing_weeks`
weeks before the base week (5 by default) -- a compact way to eyeball a
player's recent multiplier trend without opening Game Logs for every one
of them individually. Also computes a `non_td_multiplier` alongside every
`multiplier` (base row and each trailing week) -- the same fpts/salary
formula but run against non_td_fpts instead, so the frontend's Breakout
Watch panel can track a player's TD-variance-stripped value trend without
needing to recompute it from salary/non_td_fpts client-side.

Mirrors game_logs_engine.py's own conventions closely (same
"tracker + Schedule + contest_teams" inputs, same multiplier()/
pct_of_total() shared helpers from game_logs/scoring.py, same "hide a
non-DST player's 0-FPTS week" filter -- see that module's own docstring
for why) but is NOT the same shape: Game Logs shows one row per (player,
played week) across a lookback window; this tab shows exactly one row per
rostered player (the base week's own line), with the trailing weeks
pivoted into extra columns on that same row instead of extra rows.

The Game filter's own options (build_game_options, reused as-is from
game_logs_engine.py) are built from the BASE week's schedule, not the
selected week's -- the games on offer here are "which games' players am I
looking at," which is always last week's slate.
"""

from __future__ import annotations

from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.multipliers.multipliers import MultiplierRow, TrailingMultiplier
from backend.services.game_logs.game_logs_engine import ROSTER_POSITIONS
from backend.services.game_logs.scoring import multiplier as _multiplier
from backend.services.game_logs.scoring import pct_of_total as _pct
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location


def build_multiplier_rows(
    tracker_rows: list[DkPlayerRow],
    schedule_rows: list[ScheduleRow],
    week: int,
    trailing_weeks: int = 5,
    contest_teams: set[str] | None = None,
) -> tuple[list[MultiplierRow], int]:
    """Returns (rows, base_week). base_week is always `week - 1` -- this
    tab has no "reference week" concept the way Game Logs does, it's
    always strictly about reviewing last week's numbers, whether or not
    this week's own tracker rows have been added yet.

    One row per (name, position) pair that has a tracker row for
    base_week, restricted to ROSTER_POSITIONS and (when contest_teams is
    given) to a team on that set -- same roster-narrowing reasoning as
    build_game_log_rows' own `contest_teams` param, just checked against
    the base week's own team rather than a separately-tracked reference
    week (there isn't one here). A non-DST row with 0 FPTS in the base
    week is skipped (almost always "didn't play" -- see
    game_logs_engine.py's own identical rule and its docstring for why);
    DST always shows regardless of score.

    Each row's own `trailing` list always has exactly `trailing_weeks`
    entries, one per week from base_week - 1 down to
    base_week - trailing_weeks (e.g. base week 13 with trailing_weeks=5
    -> weeks 12, 11, 10, 9, 8, in that order) -- `multiplier` is None for
    any week that player has no tracker row for at all (bye, not yet
    rostered, tracker not backfilled that far), same "no data" convention
    as everywhere else, computed via the same multiplier() helper (so a
    real 0-salary row still comes back None, not a divide-by-zero)."""
    base_week = week - 1

    rows_by_name_position: dict[tuple[str, str], dict[int, DkPlayerRow]] = {}
    for r in tracker_rows:
        rows_by_name_position.setdefault((r.name, r.position), {})[r.week] = r

    rows: list[MultiplierRow] = []
    for (name, position), by_week in rows_by_name_position.items():
        if position not in ROSTER_POSITIONS:
            continue
        base = by_week.get(base_week)
        if base is None:
            continue
        if contest_teams is not None and base.team not in contest_teams:
            continue
        if position != "DST" and base.fpts == 0.0:
            continue

        schedule_entry = opponent_and_location(schedule_rows, base.team, base_week)
        opponent = schedule_entry[0] if schedule_entry else None
        game_location = schedule_entry[1] if schedule_entry else None

        trailing: list[TrailingMultiplier] = []
        for offset in range(1, trailing_weeks + 1):
            trailing_week = base_week - offset
            trailing_row = by_week.get(trailing_week)
            trailing.append(
                TrailingMultiplier(
                    week=trailing_week,
                    multiplier=_multiplier(trailing_row.fpts, trailing_row.salary) if trailing_row else None,
                    non_td_multiplier=(
                        _multiplier(trailing_row.non_td_fpts, trailing_row.salary) if trailing_row else None
                    ),
                    td_fpts=trailing_row.td_fpts if trailing_row else None,
                )
            )

        rows.append(
            MultiplierRow(
                name=name,
                position=position,
                team=base.team,
                week=base.week,
                salary=base.salary,
                opponent=opponent,
                game_location=game_location,  # type: ignore[arg-type]
                multiplier=_multiplier(base.fpts, base.salary),
                non_td_multiplier=_multiplier(base.non_td_fpts, base.salary),
                fpts=base.fpts,
                non_td_fpts=base.non_td_fpts,
                non_td_fpts_pct=_pct(base.non_td_fpts, base.fpts),
                td_fpts=base.td_fpts,
                td_fpts_pct=_pct(base.td_fpts, base.fpts),
                trailing=trailing,
            )
        )
    return rows, base_week
