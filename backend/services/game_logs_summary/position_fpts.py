"""
The Game Logs Summary tab's FPTS panels (QB, RB, WR, TE and DST, same logic):
which players had an Elite or Strong FPTS game in the window, and which
opponents have allowed such games.

Bands (minimum FPTS) per position: Elite is the dark-green band and Strong the
light-green band, as (elite_min, strong_min). Strong runs from strong_min up to
(but not including) elite_min; the two never overlap. These are this panel's own
cutoffs (DST's Strong starts at 8), separate from the FPTS shading in Game Logs.

Rows are one per player who plays this week and has an Elite or Strong game of
his own in the window, grouped by the opponent he faces. For QB/RB/WR/TE the
opponent is a defense and the right side lists the games it has allowed. For DST
the opponent is an offense: the right side lists the DST games it has allowed
(DST FPTS scored against it). Each allowed line is one player's game.

Built from the DK Players tracker (one row per player per week); the QB and RB panels' detail lines come from that position's weekly stats file (`stat_lines`). Slate scoping
and the window (`week - window_weeks .. week - 1`) match the other panels. The
Team filter keeps only rows whose team is in `team_filter`; the allowed lists
describe the opponent and are not narrowed by it.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_logs_summary.game_logs_summary import (
    FptsCell,
    FptsGroup,
    FptsLine,
    FptsRow,
    PositionFptsSummary,
)
from backend.services.game_logs_summary.shared import depth_status, is_home
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location

# (elite_min, strong_min)
FPTS_BANDS: dict[str, tuple[float, float]] = {
    "QB": (27.0, 22.0),
    "RB": (23.0, 16.0),
    "WR": (21.0, 15.0),
    "TE": (18.0, 12.0),
    "DST": (14.0, 8.0),
}
BEST_SETUP_MIN_ALLOWED = 2


def _num(x: float) -> str:
    return f"{x:g}"


def _venue(home: bool | None) -> str:
    return "" if home is None else ("vs " if home else "@ ")


def _salary(s: int) -> str:
    return f"${s / 1000:.1f}K"


def _int(line: dict, key: str) -> int | None:
    value = line.get(key)
    return int(value) if isinstance(value, (int, float)) else None


def _tds(line: dict, *keys_labels: tuple[str, str]) -> list[str]:
    """"3 pass TD" style parts, only for touchdown types actually scored."""
    out = []
    for key, label in keys_labels:
        n = _int(line, key)
        if n:
            out.append(f"{n} {label}")
    return out


def _details(position: str, stat_lines: dict[tuple[str, int], dict] | None, name: str, week: int) -> list[str]:
    """Muted lines under a game. QB: one line, "38 att · 3 pass TD · 1 rush TD"
    (attempts when the file has them, a touchdown type only if scored). RB: a
    volume line, "19 car · 5 rec / 6 tgt · 25 opp" (opportunities = carries +
    targets), then a production line, "92 rush yds · 61 rec yds · 1 rush TD ·
    1 rec TD" (a touchdown type only if scored). Empty without a stat line."""
    line = (stat_lines or {}).get((name, week))
    if not line:
        return []
    if position == "QB":
        att = _int(line, "pass_att")
        parts = ([f"{att} att"] if att is not None else []) + _tds(line, ("pass_td", "pass TD"), ("rush_td", "rush TD"))
        return [" · ".join(parts)] if parts else []
    if position == "RB":
        car, rec, tgt = _int(line, "rush_att"), _int(line, "receptions"), _int(line, "targets")
        volume = []
        if car is not None:
            volume.append(f"{car} car")
        if rec is not None and tgt is not None:
            volume.append(f"{rec} rec / {tgt} tgt")
        if car is not None and tgt is not None:
            volume.append(f"{car + tgt} opp")
        ry, cy = _int(line, "rush_yards"), _int(line, "receiving_yards")
        production = ([f"{ry} rush yds"] if ry is not None else []) + ([f"{cy} rec yds"] if cy is not None else [])
        production += _tds(line, ("rush_td", "rush TD"), ("rec_td", "rec TD"))
        return [" · ".join(x) for x in (volume, production) if x]
    if position == "DST":
        # Sacks always; the other plays only when they happened. The data has
        # no blocked-kick column, so none is shown.
        sacks = _int(line, "sacks")
        parts = [f"{sacks} sck"] if sacks is not None else []
        parts += _tds(line, ("def_int", "int"), ("fumble_recoveries", "fum rec"), ("safeties", "safety"),
                      ("def_td", "def TD"), ("ret_td", "ret TD"))
        return [" · ".join(parts)] if parts else []
    if position in ("WR", "TE"):  # same two lines for both
        tgt, rec, cy = _int(line, "targets"), _int(line, "receptions"), _int(line, "receiving_yards")
        receiving = [f"{tgt} tgt"] if tgt is not None else []
        receiving += [f"{rec} rec"] if rec is not None else []
        receiving += [f"{cy} rec yds"] if cy is not None else []
        receiving += _tds(line, ("rec_td", "rec TD"))
        car, ry = _int(line, "rush_att"), _int(line, "rush_yards")
        rushing = []
        if car:  # the rushing line only exists when he carried the ball
            rushing = [f"{car} car"] + ([f"{ry} rush yds"] if ry is not None else [])
            rushing += _tds(line, ("rush_td", "rush TD"))
        return [" · ".join(x) for x in (receiving, rushing) if x]
    return []


def build_position_fpts(
    tracker_rows: list[DkPlayerRow],
    schedule_rows: list[ScheduleRow],
    week: int,
    window_weeks: int,
    contest_teams: set[str] | None = None,
    depth_chart_snapshot: Snapshot | None = None,
    position: str = "QB",
    team_filter: set[str] | None = None,
    stat_lines: dict[tuple[str, int], dict] | None = None,
) -> PositionFptsSummary | None:
    """None when no tracker row at `position` falls in the window."""
    elite_min, strong_min = FPTS_BANDS[position]
    min_week = week - window_weeks

    def on_slate(team: str) -> bool:
        return contest_teams is None or team in contest_teams

    # (name, week, team, opponent, fpts, salary)
    games: list[tuple[str, int, str, str, float, int]] = []
    for row in tracker_rows:
        if row.position != position or not (min_week <= row.week < week):
            continue
        entry = opponent_and_location(schedule_rows, row.team, row.week)
        if entry is None or not entry[0] or entry[0] == "BYE":
            continue
        games.append((row.name, row.week, row.team, entry[0], row.fpts, row.salary))
    if not games:
        return None

    def band(f: float) -> str | None:
        if f >= elite_min:
            return "elite"
        if f >= strong_min:
            return "strong"
        return None

    player_games = {"elite": 0, "strong": 0}
    defense_allowed = {"elite": 0, "strong": 0}
    for _n, _w, team, opp, f, _s in games:
        b = band(f)
        if b is None:
            continue
        if on_slate(team):
            player_games[b] += 1
        if on_slate(opp):
            defense_allowed[b] += 1

    # What each opponent has allowed, by band, oldest first.
    def details(name: str, w: int) -> list[str]:
        return _details(position, stat_lines, name, w)

    allowed: dict[str, dict[str, list[FptsLine]]] = {}
    for name, w, team, opp, f, sal in sorted(games, key=lambda g: (g[1], g[0])):
        b = band(f)
        if b is None or not on_slate(opp):
            continue
        line = FptsLine(
            text=f"Week {w}: {name} {_venue(is_home(schedule_rows, opp, w))}{team} {f:.1f} ({_salary(sal)})",
            details=details(name, w),
        )
        allowed.setdefault(opp, {"elite": [], "strong": []})[b].append(line)

    latest: dict[str, tuple[int, str]] = {}
    for name, w, team, _o, _f, _s in games:
        if name not in latest or w > latest[name][0]:
            latest[name] = (w, team)

    by_opponent: dict[str, list[FptsRow]] = {}
    for name, (_w, team) in latest.items():
        if not on_slate(team) or (team_filter is not None and team not in team_filter):
            continue
        entry = opponent_and_location(schedule_rows, team, week)
        if entry is None or entry[0] == "BYE" or not entry[0]:
            continue
        own: dict[str, list[FptsLine]] = {"elite": [], "strong": []}
        for g in sorted((g for g in games if g[0] == name), key=lambda g: g[1]):
            b = band(g[4])
            if b is not None:
                own[b].append(
                    FptsLine(
                        text=f"Week {g[1]}: {_venue(is_home(schedule_rows, g[2], g[1]))}{g[3]} {g[4]:.1f} ({_salary(g[5])})",
                        details=details(name, g[1]),
                    )
                )
        if not own["elite"] and not own["strong"]:
            continue
        by_opponent.setdefault(entry[0], []).append(
            FptsRow(
                name=name,
                team=team,
                status=depth_status(depth_chart_snapshot, team, position, name),
                elite=FptsCell(count=len(own["elite"]), lines=own["elite"]),
                strong=FptsCell(count=len(own["strong"]), lines=own["strong"]),
            )
        )

    groups: list[FptsGroup] = []
    for opp, rows in by_opponent.items():
        got = allowed.get(opp, {"elite": [], "strong": []})
        rows.sort(key=lambda r: (-(r.elite.count + r.strong.count), r.name))
        groups.append(
            FptsGroup(
                opponent=opp,
                row_count=len(rows),
                allowed_total=len(got["elite"]) + len(got["strong"]),
                allowed_elite=FptsCell(count=len(got["elite"]), lines=got["elite"]),
                allowed_strong=FptsCell(count=len(got["strong"]), lines=got["strong"]),
                rows=rows,
            )
        )
    groups.sort(key=lambda g: (-g.allowed_total, g.opponent))

    elite_label = f"{_num(elite_min)}+"
    strong_label = f"{_num(strong_min)}-{_num(elite_min - 0.1)}"
    first, last = min(g[1] for g in games), max(g[1] for g in games)
    return PositionFptsSummary(
        position=position,
        opponent_label="Opp offense" if position == "DST" else "Opp D",
        weeks_label=f"Week {first}" if first == last else f"Weeks {first}-{last}",
        elite_label=elite_label,
        strong_label=strong_label,
        player_games_elite=player_games["elite"],
        player_games_strong=player_games["strong"],
        allowed_elite=defense_allowed["elite"],
        allowed_strong=defense_allowed["strong"],
        best_setups=[
            f"{r.name} vs {g.opponent} ({g.allowed_total} allowed {_num(strong_min)}+)"
            for g in groups
            if g.allowed_total >= BEST_SETUP_MIN_ALLOWED
            for r in g.rows
        ],
        row_count=sum(g.row_count for g in groups),
        groups=groups,
    )
