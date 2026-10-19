"""
The Game Logs Summary tab's slate-wide "RB receiving" panel, modeled on the
RB rushing panel (rb_rushing.py): which RBs have 50+ receiving yards in a game
in the window, which defenses have allowed 50+ receiving yards to a team's
RBs, and which RBs play one of those defenses this week. A second pair of
columns does the same for receiving TDs (1+ per game).

Same rules as the rushing panel, by request:

- A RB gets a row if he has ANY 50+ receiving-yard game of his own (fullbacks
  count as RBs; no "primary RB" rule).
- A DEFENSE'S allowed games combine the offense's RBs: for each (defense,
  week) every RB's receiving yards are summed and that total is compared with
  the 50-yard bar; each allowed game lists every RB's own yards. Counts are
  games, not players.
- TD columns ride along on those rows; a RB isn't added just for scoring a
  receiving TD.

Scope and window match the other panels: `contest_teams` limits RBs and
defenses to the contest's slate, and the window is `week - window_weeks ..
week - 1`.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.game_logs_summary.game_logs_summary import (
    RbReceiver,
    RbReceivingAllowedGame,
    RbReceivingGame,
    RbReceivingRow,
    RbReceivingSummary,
    RbRushingSetup,
)
from backend.services.game_logs_summary.shared import (
    TdLine,
    depth_status,
    is_home,
    rb_allowed_td_games,
    rb_own_td_games,
)
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location

REC_YDS_BAR = 50
# A defense needs this many allowed games to appear in "best setups".
BEST_SETUP_MIN_ALLOWED = 2


def build_rb_receiving(
    rb_stat_lines: dict[tuple[str, int], dict[str, int | float | str]],
    schedule_rows: list[ScheduleRow],
    week: int,
    window_weeks: int,
    contest_teams: set[str] | None = None,
    depth_chart_snapshot: Snapshot | None = None,
) -> RbReceivingSummary | None:
    """None when no RB line with a receiving-yards value falls in the window."""
    min_week = week - window_weeks

    def on_slate(team: str) -> bool:
        return contest_teams is None or team in contest_teams

    # (name, week, team, opponent, receiving yards) for every usable line.
    lines: list[tuple[str, int, str, str, int]] = []
    td_lines: list[TdLine] = []
    for (name, line_week), line in rb_stat_lines.items():
        if not (min_week <= line_week < week):
            continue
        team = str(line.get("team") or "")
        opponent = str(line.get("opponent") or "")
        yards = line.get("receiving_yards")
        if not team or not opponent or not isinstance(yards, (int, float)):
            continue
        lines.append((name, line_week, team, opponent, int(yards)))
        tds = line.get("rec_td")
        td_lines.append((name, line_week, team, opponent, int(tds) if isinstance(tds, (int, float)) else 0))
    if not lines:
        return None

    rb_50 = sum(1 for _, _, team, _, y in lines if on_slate(team) and y >= REC_YDS_BAR)
    allowed_td_by_defense = rb_allowed_td_games(td_lines, schedule_rows, on_slate)
    rb_games_td = sum(1 for _, _, team, _, td in td_lines if on_slate(team) and td >= 1)
    def_games_td = sum(len(games) for games in allowed_td_by_defense.values())

    # (defense, week) -> that offense's RBs and their receiving yards.
    game_receivers: dict[tuple[str, int], list[RbReceiver]] = {}
    game_team: dict[tuple[str, int], str] = {}
    for name, line_week, team, opponent, yards in lines:
        key = (opponent, line_week)
        game_receivers.setdefault(key, []).append(RbReceiver(name=name, team=team, rec_yds=yards))
        game_team[key] = team

    allowed_by_defense: dict[str, list[RbReceivingAllowedGame]] = {}
    def_50 = 0
    for (defense, line_week), receivers in sorted(game_receivers.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        total = sum(r.rec_yds for r in receivers)
        if total < REC_YDS_BAR or not on_slate(defense):
            continue
        def_50 += 1
        allowed_by_defense.setdefault(defense, []).append(
            RbReceivingAllowedGame(
                week=line_week,
                team=game_team[(defense, line_week)],
                defense_is_home=is_home(schedule_rows, defense, line_week),
                total_yds=total,
                receivers=sorted((r for r in receivers if r.rec_yds > 0), key=lambda r: (-r.rec_yds, r.name)),
            )
        )

    # A RB's current team is the team on his most recent line in the window.
    latest_line: dict[str, tuple[int, str]] = {}
    for name, line_week, team, _, _ in lines:
        if name not in latest_line or line_week > latest_line[name][0]:
            latest_line[name] = (line_week, team)

    rows: list[RbReceivingRow] = []
    for name, (_, team) in latest_line.items():
        if not on_slate(team):
            continue
        entry = opponent_and_location(schedule_rows, team, week)
        if entry is None or entry[0] == "BYE" or not entry[0]:
            continue
        opponent = entry[0]

        own_games = sorted((l for l in lines if l[0] == name and l[4] >= REC_YDS_BAR), key=lambda l: l[1])
        if not own_games:
            continue
        rows.append(
            RbReceivingRow(
                name=name,
                team=team,
                status=depth_status(depth_chart_snapshot, team, "RB", name),
                opponent=opponent,
                games_50=[
                    RbReceivingGame(week=w, opponent=opp, is_home=is_home(schedule_rows, t, w), rec_yds=y)
                    for _, w, t, opp, y in own_games
                ],
                opponent_allowed=allowed_by_defense.get(opponent, []),
                td_games=rb_own_td_games(name, td_lines, schedule_rows),
                opponent_allowed_td=allowed_td_by_defense.get(opponent, []),
            )
        )

    rows.sort(key=lambda r: (-len(r.opponent_allowed), -len(r.games_50), r.name))
    best_setups = [
        RbRushingSetup(name=r.name, opponent=r.opponent, allowed_count=len(r.opponent_allowed))
        for r in rows
        if len(r.opponent_allowed) >= BEST_SETUP_MIN_ALLOWED
    ]

    return RbReceivingSummary(
        first_week=min(l[1] for l in lines),
        through_week=max(l[1] for l in lines),
        rb_games_50=rb_50,
        defense_allowed_50=def_50,
        rb_games_td=rb_games_td,
        defense_allowed_td=def_games_td,
        best_setups=best_setups,
        rows=rows,
    )
