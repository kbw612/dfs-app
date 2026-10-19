"""
The Game Logs Summary tab's slate-wide "RB rushing yards" panel, modeled on
the QB passing panel (qb_passing.py): which RBs have rushed for 100+ or
75-99 yards in the window, which defenses have allowed 75+ rushing yards,
and which RBs play one of those defenses this week.

Built from the RB stat-line file (fullbacks included -- the file's FB lines
count as RBs), one line per player per week with team, opponent and
`rush_yards`. Two differences from the QB panel, both by request:

- A RB gets a row if he has ANY 75+ game of his own (there is no "primary
  RB" rule -- backfields share carries, so every RB who cleared the bar
  counts, one game each).
- A DEFENSE'S allowed games combine the offense's RBs: for each (defense,
  week) the yards of every RB that team used are summed, and that combined
  total is what is bucketed (100+, or 75-99 which excludes the 100+ games).
  Each allowed game still lists every RB's own yards. So a defense that gave
  60 and 45 to two backs allowed one 100+ game, even though neither back
  reached 75 alone.

Scope and window match the QB panel: `contest_teams` limits RBs and defenses
to the selected contest's slate, and the window is `week - window_weeks ..
week - 1`. The two buckets never overlap.

The TD columns follow the same split: a RB's own games with 1+ rushing TD,
and the games a defense allowed 1+ rushing TD to a team's RBs combined (see
shared.py). They ride along on the yardage rows -- a RB is not added to the
table just for scoring a TD, since nearly every back would qualify.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.game_logs_summary.game_logs_summary import (
    RbRusher,
    RbRushingAllowedGame,
    RbRushingGame,
    RbRushingRow,
    RbRushingSetup,
    RbRushingSummary,
)
from backend.services.game_logs_summary.shared import (
    TdLine,
    depth_status,
    is_home,
    rb_allowed_td_games,
    rb_own_td_games,
)
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location

RUSH_YDS_HIGH = 100
RUSH_YDS_MID = 75
# A defense needs this many allowed games to appear in "best setups".
BEST_SETUP_MIN_ALLOWED = 2


def build_rb_rushing(
    rb_stat_lines: dict[tuple[str, int], dict[str, int | float | str]],
    schedule_rows: list[ScheduleRow],
    week: int,
    window_weeks: int,
    contest_teams: set[str] | None = None,
    depth_chart_snapshot: Snapshot | None = None,
) -> RbRushingSummary | None:
    """None when no RB line falls in the window (nothing to show)."""
    min_week = week - window_weeks

    def on_slate(team: str) -> bool:
        return contest_teams is None or team in contest_teams

    # (name, week, team, opponent, yards) for every usable line in the window.
    lines: list[tuple[str, int, str, str, int]] = []
    # Same lines with the rushing-TD count, for the TD columns.
    td_lines: list[TdLine] = []
    for (name, line_week), line in rb_stat_lines.items():
        if not (min_week <= line_week < week):
            continue
        team = str(line.get("team") or "")
        opponent = str(line.get("opponent") or "")
        yards = line.get("rush_yards")
        if not team or not opponent or not isinstance(yards, (int, float)):
            continue
        lines.append((name, line_week, team, opponent, int(yards)))
        tds = line.get("rush_td")
        td_lines.append((name, line_week, team, opponent, int(tds) if isinstance(tds, (int, float)) else 0))
    if not lines:
        return None

    allowed_td_by_defense = rb_allowed_td_games(td_lines, schedule_rows, on_slate)
    rb_games_td = sum(1 for _, _, team, _, td in td_lines if on_slate(team) and td >= 1)
    def_games_td = sum(len(games) for games in allowed_td_by_defense.values())

    rb_100 = sum(1 for _, _, team, _, y in lines if on_slate(team) and y >= RUSH_YDS_HIGH)
    rb_mid = sum(1 for _, _, team, _, y in lines if on_slate(team) and RUSH_YDS_MID <= y < RUSH_YDS_HIGH)

    # (defense, week) -> that offense's RBs and their yards. All RB lines are
    # included (not just 75+ ones) since the defense's number is the combined
    # total; a team's RBs that week share one opponent, so (defense, week)
    # identifies one team-game.
    game_rushers: dict[tuple[str, int], list[RbRusher]] = {}
    game_team: dict[tuple[str, int], str] = {}
    for name, line_week, team, opponent, yards in lines:
        key = (opponent, line_week)
        game_rushers.setdefault(key, []).append(RbRusher(name=name, team=team, rush_yds=yards))
        game_team[key] = team

    allowed_by_defense: dict[str, list[RbRushingAllowedGame]] = {}
    def_100 = 0
    def_mid = 0
    for (defense, line_week), rushers in sorted(game_rushers.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        total = sum(r.rush_yds for r in rushers)
        if total < RUSH_YDS_MID or not on_slate(defense):
            continue
        if total >= RUSH_YDS_HIGH:
            def_100 += 1
        else:
            def_mid += 1
        allowed_by_defense.setdefault(defense, []).append(
            RbRushingAllowedGame(
                week=line_week,
                team=game_team[(defense, line_week)],
                defense_is_home=is_home(schedule_rows, defense, line_week),
                total_yds=total,
                # Zero-yard backs add nothing to the combined total, so leave
                # them off the list.
                rushers=sorted((r for r in rushers if r.rush_yds > 0), key=lambda r: (-r.rush_yds, r.name)),
            )
        )

    # A RB's current team is the team on his most recent line in the window.
    latest_line: dict[str, tuple[int, str]] = {}
    for name, line_week, team, _, _ in lines:
        if name not in latest_line or line_week > latest_line[name][0]:
            latest_line[name] = (line_week, team)

    rows: list[RbRushingRow] = []
    for name, (_, team) in latest_line.items():
        if not on_slate(team):
            continue
        entry = opponent_and_location(schedule_rows, team, week)
        if entry is None or entry[0] == "BYE" or not entry[0]:
            continue
        opponent = entry[0]

        own_games = sorted((l for l in lines if l[0] == name and l[4] >= RUSH_YDS_MID), key=lambda l: l[1])
        if not own_games:
            continue
        over_100 = [
            RbRushingGame(week=w, opponent=opp, is_home=is_home(schedule_rows, t, w), rush_yds=y)
            for _, w, t, opp, y in own_games
            if y >= RUSH_YDS_HIGH
        ]
        mid = [
            RbRushingGame(week=w, opponent=opp, is_home=is_home(schedule_rows, t, w), rush_yds=y)
            for _, w, t, opp, y in own_games
            if y < RUSH_YDS_HIGH
        ]
        rows.append(
            RbRushingRow(
                name=name,
                team=team,
                status=depth_status(depth_chart_snapshot, team, "RB", name),
                opponent=opponent,
                over_100=over_100,
                range_75_99=mid,
                opponent_allowed=allowed_by_defense.get(opponent, []),
                td_games=rb_own_td_games(name, td_lines, schedule_rows),
                opponent_allowed_td=allowed_td_by_defense.get(opponent, []),
            )
        )

    rows.sort(key=lambda r: (-len(r.opponent_allowed), -(len(r.over_100) + len(r.range_75_99)), r.name))
    best_setups = [
        RbRushingSetup(name=r.name, opponent=r.opponent, allowed_count=len(r.opponent_allowed))
        for r in rows
        if len(r.opponent_allowed) >= BEST_SETUP_MIN_ALLOWED
    ]

    return RbRushingSummary(
        first_week=min(l[1] for l in lines),
        through_week=max(l[1] for l in lines),
        rb_games_100=rb_100,
        rb_games_75_99=rb_mid,
        defense_allowed_100=def_100,
        defense_allowed_75_99=def_mid,
        rb_games_td=rb_games_td,
        defense_allowed_td=def_games_td,
        best_setups=best_setups,
        rows=rows,
    )
