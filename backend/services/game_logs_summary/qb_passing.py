"""
The Game Logs Summary tab's slate-wide "QB passing yards" panel: which QBs have thrown
for 300+ or 265-299 yards in the window, which defenses have allowed 265+
to a QB, and which QBs play one of those defenses this week.

Everything comes from the QB stat-line file (one line per QB per week, with
the QB's team, opponent and passing yards) -- a defense's "allowed" list is
just those same lines grouped by the opponent. Home/away comes from the
Schedule file, since a stat line doesn't say.

Scope matches the example this was built from ("main-slate quarterbacks ...
main-slate defenses"): when `contest_teams` is given, a QB counts only if
his team is on the slate and a defense only if it is. The window is
`week - window_weeks .. week - 1`, same as every other Game Preview
section. The two buckets never overlap: 300+ is its own bucket and "265-299"
excludes it, but the per-defense allowed list is 265+ (300+ included), since
that is the question being asked of a defense.

A QB gets a table row when he plays this week and either has a 265+ game of
his own, or is his team's primary QB (most pass attempts in the window) and
his opponent allowed at least one -- so a backup who threw a few passes, or
a QB with neither signal, is left out as noise.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.game_logs_summary.game_logs_summary import (
    QbPassingAllowedGame,
    QbPassingGame,
    QbPassingSummary,
    QbPassingRow,
    QbPassingSetup,
)
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location

PASS_YDS_HIGH = 300
PASS_YDS_MID = 265
# A defense needs this many 265+ games allowed to appear in "best setups".
BEST_SETUP_MIN_ALLOWED = 2


def _is_home(schedule_rows: list[ScheduleRow], team: str, week: int) -> bool | None:
    entry = opponent_and_location(schedule_rows, team, week)
    if entry is None or entry[1] not in ("Home", "Away"):
        return None
    return entry[1] == "Home"


def _qb_status(snapshot: Snapshot | None, team: str, name: str) -> str | None:
    if snapshot is None:
        return None
    team_row = next((t for t in snapshot.teams if t.team_abbrev == team), None)
    if team_row is None:
        return None
    for player in team_row.positions.get("QB", []):
        if player.player == name:
            return player.status
    return None


def build_qb_passing(
    qb_stat_lines: dict[tuple[str, int], dict[str, int | float | str]],
    schedule_rows: list[ScheduleRow],
    week: int,
    window_weeks: int,
    contest_teams: set[str] | None = None,
    depth_chart_snapshot: Snapshot | None = None,
) -> QbPassingSummary | None:
    """None when no QB line falls in the window (nothing to show)."""
    min_week = week - window_weeks

    def on_slate(team: str) -> bool:
        return contest_teams is None or team in contest_teams

    # (name, week, team, opponent, yards) for every usable line in the window.
    lines: list[tuple[str, int, str, str, int]] = []
    attempts: dict[str, float] = {}
    for (name, line_week), line in qb_stat_lines.items():
        if not (min_week <= line_week < week):
            continue
        team = str(line.get("team") or "")
        opponent = str(line.get("opponent") or "")
        yards = line.get("pass_yds")
        if not team or not opponent or not isinstance(yards, (int, float)):
            continue
        lines.append((name, line_week, team, opponent, int(yards)))
        att = line.get("pass_att")
        attempts[name] = attempts.get(name, 0.0) + (float(att) if isinstance(att, (int, float)) else 0.0)
    if not lines:
        return None

    qb_300 = sum(1 for _, _, team, _, y in lines if on_slate(team) and y >= PASS_YDS_HIGH)
    qb_mid = sum(1 for _, _, team, _, y in lines if on_slate(team) and PASS_YDS_MID <= y < PASS_YDS_HIGH)
    def_300 = sum(1 for _, _, _, opp, y in lines if on_slate(opp) and y >= PASS_YDS_HIGH)
    def_mid = sum(1 for _, _, _, opp, y in lines if on_slate(opp) and PASS_YDS_MID <= y < PASS_YDS_HIGH)

    # Every 265+ game a defense allowed, oldest week first (passer name as
    # the tie-break so the order is stable).
    allowed_by_defense: dict[str, list[QbPassingAllowedGame]] = {}
    for name, line_week, team, opponent, yards in sorted(lines, key=lambda l: (l[1], l[0])):
        if yards >= PASS_YDS_MID and on_slate(opponent):
            allowed_by_defense.setdefault(opponent, []).append(
                QbPassingAllowedGame(
                    week=line_week,
                    passer=name,
                    passer_team=team,
                    defense_is_home=_is_home(schedule_rows, opponent, line_week),
                    pass_yds=yards,
                )
            )

    # A QB's current team is the team on his most recent line in the window.
    latest_line: dict[str, tuple[int, str]] = {}
    for name, line_week, team, _, _ in lines:
        if name not in latest_line or line_week > latest_line[name][0]:
            latest_line[name] = (line_week, team)

    # Each team's primary QB is whoever threw the most passes for it in the
    # window. Only he gets a row on the strength of his opponent alone; a
    # backup who threw a handful of passes appears only if he has a 265+
    # game of his own.
    primary_qb: dict[str, str] = {}
    for name, (_, team) in latest_line.items():
        current = primary_qb.get(team)
        if current is None or attempts.get(name, 0.0) > attempts.get(current, 0.0):
            primary_qb[team] = name

    rows: list[QbPassingRow] = []
    for name, (_, team) in latest_line.items():
        if not on_slate(team):
            continue
        entry = opponent_and_location(schedule_rows, team, week)
        if entry is None or entry[0] == "BYE" or not entry[0]:
            continue
        opponent = entry[0]

        own_games = sorted(
            (l for l in lines if l[0] == name and l[4] >= PASS_YDS_MID), key=lambda l: l[1]
        )
        over_300 = [
            QbPassingGame(week=w, opponent=opp, is_home=_is_home(schedule_rows, t, w), pass_yds=y)
            for _, w, t, opp, y in own_games
            if y >= PASS_YDS_HIGH
        ]
        mid = [
            QbPassingGame(week=w, opponent=opp, is_home=_is_home(schedule_rows, t, w), pass_yds=y)
            for _, w, t, opp, y in own_games
            if y < PASS_YDS_HIGH
        ]
        allowed = allowed_by_defense.get(opponent, [])
        is_primary = primary_qb.get(team) == name
        if not over_300 and not mid and not (is_primary and allowed):
            continue
        rows.append(
            QbPassingRow(
                name=name,
                team=team,
                status=_qb_status(depth_chart_snapshot, team, name),
                opponent=opponent,
                over_300=over_300,
                range_265_299=mid,
                opponent_allowed=allowed,
            )
        )

    rows.sort(key=lambda r: (-len(r.opponent_allowed), -(len(r.over_300) + len(r.range_265_299)), r.name))
    best_setups = [
        QbPassingSetup(name=r.name, opponent=r.opponent, allowed_count=len(r.opponent_allowed))
        for r in rows
        if len(r.opponent_allowed) >= BEST_SETUP_MIN_ALLOWED
    ]

    return QbPassingSummary(
        first_week=min(l[1] for l in lines),
        through_week=max(l[1] for l in lines),
        qb_games_300=qb_300,
        qb_games_265_299=qb_mid,
        defense_allowed_300=def_300,
        defense_allowed_265_299=def_mid,
        best_setups=best_setups,
        rows=rows,
    )
