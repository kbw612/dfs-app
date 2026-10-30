"""
Small helpers shared by the Game Logs Summary panels (QB passing, RB rushing).
"""

from __future__ import annotations

from collections.abc import Callable

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.game_logs_summary.game_logs_summary import RbAllowedTdGame, RbTdGame, RbTdScorer
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location

# (name, week, team, opponent, touchdowns) -- one RB's TD count in one game.
TdLine = tuple[str, int, str, str, int]


def rb_own_td_games(name: str, td_lines: list[TdLine], schedule_rows: list[ScheduleRow]) -> list[RbTdGame]:
    """His own games with 1+ TDs, oldest week first."""
    return [
        RbTdGame(week=w, opponent=opp, is_home=is_home(schedule_rows, t, w), td=td)
        for n, w, t, opp, td in sorted(td_lines, key=lambda l: l[1])
        if n == name and td >= 1
    ]


def rb_allowed_td_games(
    td_lines: list[TdLine], schedule_rows: list[ScheduleRow], on_slate: Callable[[str], bool]
) -> dict[str, list[RbAllowedTdGame]]:
    """Per defense, each game where a team's RBs COMBINED for 1+ TDs (counted
    as games, not scorers), oldest week first, each with the scoring backs
    listed. Every RB line is passed in, scorers or not, since a (defense,
    week) pair identifies one team-game."""
    grouped: dict[tuple[str, int], list[TdLine]] = {}
    for line in td_lines:
        grouped.setdefault((line[3], line[1]), []).append(line)
    result: dict[str, list[RbAllowedTdGame]] = {}
    for (defense, week), group in sorted(grouped.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        total = sum(l[4] for l in group)
        if total < 1 or not on_slate(defense):
            continue
        result.setdefault(defense, []).append(
            RbAllowedTdGame(
                week=week,
                team=group[0][2],
                defense_is_home=is_home(schedule_rows, defense, week),
                total_td=total,
                scorers=sorted(
                    (RbTdScorer(name=l[0], team=l[2], td=l[4]) for l in group if l[4] > 0),
                    key=lambda s: (-s.td, s.name),
                ),
            )
        )
    return result


def is_home(schedule_rows: list[ScheduleRow], team: str, week: int) -> bool | None:
    """True/False for that team's home/away status that week, None when the
    Schedule file has no row for it (or it is a bye)."""
    entry = opponent_and_location(schedule_rows, team, week)
    if entry is None or entry[1] not in ("Home", "Away"):
        return None
    return entry[1] == "Home"


def depth_status(snapshot: Snapshot | None, team: str, position: str, name: str) -> str | None:
    """Depth-chart injury status code for `name` at `position` on `team`, or
    None if there is none (or no snapshot / no match)."""
    if snapshot is None:
        return None
    team_row = next((t for t in snapshot.teams if t.team_abbrev == team), None)
    if team_row is None:
        return None
    for player in team_row.positions.get(position, []):
        if player.player == name:
            return player.status
    return None


def salary_lookup(players) -> Callable[[str, str], int | None]:
    """(name, team) -> this week's salary from the contest salary file's
    players, matching names the way the rest of the app does."""
    from backend.services.shared.name_match import normalize_player_name

    table = {(normalize_player_name(p.player), p.team): p.salary for p in players}
    return lambda name, team: table.get((normalize_player_name(name), team))


def attach_salaries(summaries, lookup: Callable[[str, str], int | None]) -> None:
    """Fills `salary` on every row of the given panel summaries (None entries
    are skipped). FPTS rows are grouped under opponents; the others are flat."""
    for summary in summaries:
        if summary is None:
            continue
        rows = summary.rows if hasattr(summary, "rows") else [r for g in summary.groups for r in g.rows]
        for row in rows:
            row.salary = lookup(row.name, row.team)
