"""
The Game Logs Summary tab's salary-multiplier panels (one each for QB, RB, WR
and TE, same logic): which players at the position returned
3x+ (split into 4x+ and 3-3.99x) or 2.5x+ on non-TD points in a game in
the window, which defenses allowed those games, and which RBs play one of
those defenses this week.

Built from the DK Players tracker (one row per player per week with salary,
FPTS and non-TD FPTS), one position at a time. multiplier = FPTS / (salary / 1000)
(scoring.multiplier); the non-TD multiplier uses non-TD FPTS the same way,
so it shows what a back returned without any touchdown points.

Unlike the yardage panels, the defense side is NOT combined across a team's
players: a salary multiplier belongs to one priced player, so each allowed line
is one player's game. Counts are those player games. The 4x+ and 3-3.99x buckets
never overlap; the non-TD 2.5x+ column holds only games that are NOT already in either of
those (a 3x+ game never also appears as non-TD).

A player gets a row when he plays this week and has a 3x+ game or a non-TD 2.5x+
game of his own in the window. Slate scoping, the window
(`week - window_weeks .. week - 1`) and the 2-or-more "best setups" rule
match the other panels.
"""

from __future__ import annotations

from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.game_logs_summary.game_logs_summary import (
    PositionMultiplierAllowedGame,
    PositionMultiplierGame,
    PositionMultiplierRow,
    PositionMultiplierSummary,
    RbRushingSetup,
)
from backend.services.game_logs.scoring import multiplier
from backend.services.game_logs_summary.shared import depth_status, is_home
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location

MULT_HIGH = 4.0
MULT_MID = 3.0
NON_TD_MULT_BAR = 2.5
BEST_SETUP_MIN_ALLOWED = 2


def build_position_multipliers(
    tracker_rows: list[DkPlayerRow],
    schedule_rows: list[ScheduleRow],
    week: int,
    window_weeks: int,
    contest_teams: set[str] | None = None,
    depth_chart_snapshot: Snapshot | None = None,
    position: str = "RB",
) -> PositionMultiplierSummary | None:
    """None when no priced tracker row at `position` (QB/RB/WR/TE) falls in the window."""
    min_week = week - window_weeks

    def on_slate(team: str) -> bool:
        return contest_teams is None or team in contest_teams

    # (name, week, team, opponent, multiplier, non-TD multiplier, salary)
    games: list[tuple[str, int, str, str, float, float, int]] = []
    for row in tracker_rows:
        if row.position != position or not (min_week <= row.week < week):
            continue
        mult = multiplier(row.fpts, row.salary)
        non_td = multiplier(row.non_td_fpts, row.salary)
        if mult is None or non_td is None:
            continue
        entry = opponent_and_location(schedule_rows, row.team, row.week)
        if entry is None or not entry[0] or entry[0] == "BYE":
            continue
        games.append((row.name, row.week, row.team, entry[0], mult, non_td, row.salary))
    if not games:
        return None

    def is_non_td(m: float, nt: float) -> bool:
        """Non-TD 2.5x+ bucket: only games NOT already in the 4x+ or 3-3.99x
        buckets, so a game never shows in both the multiplier and non-TD columns."""
        return nt >= NON_TD_MULT_BAR and m < MULT_MID

    def is_4x(m: float) -> bool:
        return m >= MULT_HIGH

    def is_mid(m: float) -> bool:
        return MULT_MID <= m < MULT_HIGH

    p_4x = sum(1 for g in games if on_slate(g[2]) and is_4x(g[4]))
    p_mid = sum(1 for g in games if on_slate(g[2]) and is_mid(g[4]))
    p_nt = sum(1 for g in games if on_slate(g[2]) and is_non_td(g[4], g[5]))
    def_4x = sum(1 for g in games if on_slate(g[3]) and is_4x(g[4]))
    def_mid = sum(1 for g in games if on_slate(g[3]) and is_mid(g[4]))
    def_nt = sum(1 for g in games if on_slate(g[3]) and is_non_td(g[4], g[5]))

    allowed: dict[str, list[PositionMultiplierAllowedGame]] = {}
    allowed_nt: dict[str, list[PositionMultiplierAllowedGame]] = {}
    for name, w, team, opp, m, nt, sal in sorted(games, key=lambda g: (g[1], g[0])):
        if not on_slate(opp):
            continue
        if m >= MULT_MID:
            allowed.setdefault(opp, []).append(
                PositionMultiplierAllowedGame(
                    week=w, player=name, player_team=team, defense_is_home=is_home(schedule_rows, opp, w), multiplier=round(m, 2), salary=sal
                )
            )
        if is_non_td(m, nt):
            allowed_nt.setdefault(opp, []).append(
                PositionMultiplierAllowedGame(
                    week=w, player=name, player_team=team, defense_is_home=is_home(schedule_rows, opp, w), multiplier=round(nt, 2), salary=sal
                )
            )

    latest: dict[str, tuple[int, str]] = {}
    for name, w, team, _, _, _, _ in games:
        if name not in latest or w > latest[name][0]:
            latest[name] = (w, team)

    rows: list[PositionMultiplierRow] = []
    for name, (_, team) in latest.items():
        if not on_slate(team):
            continue
        entry = opponent_and_location(schedule_rows, team, week)
        if entry is None or entry[0] == "BYE" or not entry[0]:
            continue
        own = sorted((g for g in games if g[0] == name), key=lambda g: g[1])

        def mk(g: tuple[str, int, str, str, float, float, int], value: float) -> PositionMultiplierGame:
            return PositionMultiplierGame(
                week=g[1], opponent=g[3], is_home=is_home(schedule_rows, g[2], g[1]), multiplier=round(value, 2), salary=g[6]
            )

        over_4x = [mk(g, g[4]) for g in own if is_4x(g[4])]
        mid = [mk(g, g[4]) for g in own if is_mid(g[4])]
        non_td = [mk(g, g[5]) for g in own if is_non_td(g[4], g[5])]
        if not over_4x and not mid and not non_td:
            continue
        rows.append(
            PositionMultiplierRow(
                name=name,
                team=team,
                status=depth_status(depth_chart_snapshot, team, position, name),
                opponent=entry[0],
                over_4x=over_4x,
                range_3x_399=mid,
                non_td_2_5x=non_td,
                opponent_allowed=allowed.get(entry[0], []),
                opponent_allowed_non_td=allowed_nt.get(entry[0], []),
            )
        )

    # Players facing the same defense sit together (the panel groups them under
    # that defense); groups with the most allowed 3x+ games come first.
    rows.sort(
        key=lambda r: (-len(r.opponent_allowed), r.opponent, -(len(r.over_4x) + len(r.range_3x_399)), r.name)
    )
    best_setups = [
        RbRushingSetup(name=r.name, opponent=r.opponent, allowed_count=len(r.opponent_allowed))
        for r in rows
        if len(r.opponent_allowed) >= BEST_SETUP_MIN_ALLOWED
    ]

    return PositionMultiplierSummary(
        first_week=min(g[1] for g in games),
        through_week=max(g[1] for g in games),
        position=position,
        player_games_4x=p_4x,
        player_games_3x_399=p_mid,
        player_games_non_td_2_5x=p_nt,
        defense_allowed_4x=def_4x,
        defense_allowed_3x_399=def_mid,
        defense_allowed_non_td_2_5x=def_nt,
        best_setups=best_setups,
        rows=rows,
    )
