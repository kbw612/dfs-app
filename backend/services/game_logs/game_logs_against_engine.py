"""
Computes the Game Logs Against tab's rows -- the inverse of Game Logs
(game_logs_engine.py): instead of a team's own roster's scoring history,
this shows how every OPPOSING player performed in their own game against
a given team, across that team's last `lookback_weeks` games. Mirrors the
person's own prior DKPlayersWeeksScoringAgainst.ipynb workflow exactly
(same "walk this team's own recent schedule, pull whoever they played
each week, list that opponent's real box score" approach) -- ported to
this app's own DK Players tracker + Schedule file instead of a one-off
GitHub CSV pull.

Unlike Game Logs, there's no "currently rostered" snapshot concept here --
the schedule itself (not the tracker) drives which weeks/opponents to
look at, so a since-released/traded player who faced this team earlier in
the season still shows up (their tracker row for that specific week is
what's read, not their team's rows -- see build_game_logs_against_rows).
DST is included and exempt from the zero-FPTS filter, same convention and
same reasoning as Game Logs' own ROSTER_POSITIONS -- see this module's
reuse of that constant.
"""

from __future__ import annotations

from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_logs.game_logs_against import GameLogAgainstRow
from backend.services.game_logs.game_logs_engine import ROSTER_POSITIONS
from backend.services.game_logs.scoring import multiplier, pct_of_total
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location


def build_game_logs_against_rows(
    tracker_rows: list[DkPlayerRow],
    schedule_rows: list[ScheduleRow],
    team: str,
    week: int,
    lookback_weeks: int,
) -> list[GameLogAgainstRow]:
    """`team`'s own schedule rows in [week - lookback_weeks, week) (i.e.
    the same "strictly before the target week" window Game Logs uses,
    just anchored on `week` directly rather than a tracker-derived
    reference week -- there's no roster snapshot here for `week` itself to
    fall back from) name each week's opponent; for each such week/opponent
    pair, every one of that opponent's tracker rows for that exact week is
    a real "this player's stats from their game against `team`" data
    point. A bye week (or a week the Schedule file has no row for at all)
    simply contributes no opponent to look up, same gap Game Logs' own
    week-skipping shows.

    Sorted most-recent-week-first, matching the person's own script's
    Team/Week-descending sort -- callers that want a different order
    (e.g. by position, then FPTS) resort client-side, same convention as
    Game Logs' own frontend-side grouping."""
    min_week = week - lookback_weeks
    opponent_by_week: dict[int, str] = {
        r.week: r.opponent
        for r in schedule_rows
        if r.team == team and min_week <= r.week < week and r.opponent not in ("BYE", "")
    }

    rows: list[GameLogAgainstRow] = []
    for wk in sorted(opponent_by_week, reverse=True):
        opponent = opponent_by_week[wk]
        for r in tracker_rows:
            if r.team != opponent or r.week != wk or r.position not in ROSTER_POSITIONS:
                continue
            if r.position != "DST" and r.fpts == 0.0:
                continue
            schedule_entry = opponent_and_location(schedule_rows, r.team, r.week)
            game_location = schedule_entry[1] if schedule_entry else None
            rows.append(
                GameLogAgainstRow(
                    against_team=team,
                    week=r.week,
                    name=r.name,
                    position=r.position,
                    salary=r.salary,
                    game_location=game_location,  # type: ignore[arg-type]
                    multiplier=multiplier(r.fpts, r.salary),
                    fpts=r.fpts,
                    non_td_fpts=r.non_td_fpts,
                    non_td_fpts_pct=pct_of_total(r.non_td_fpts, r.fpts),
                    td_fpts=r.td_fpts,
                    td_fpts_pct=pct_of_total(r.td_fpts, r.fpts),
                )
            )
    return rows
