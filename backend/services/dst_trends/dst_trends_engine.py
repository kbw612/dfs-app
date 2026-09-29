"""
Computes DST Trends' two leaderboards (see backend/schemas/dst_trends/
dst_trends.py's own docstring) from FantasyData_DSTs.csv's own stat lines
(backend/services/dk_players/weekly_stats_loader.py's load_weekly_stat_lines
output) -- one file, no QB/RB/WR/TE join needed, because every DST row
already carries an "opponent" field naming the offense it played that
week. A DST's own DEF_SCK/DEF_INT/FR that week is simultaneously "sacks/
takeaways THIS defense generated" (attributed to its own team, feeding the
`forcing` leaderboard) and "sacks/turnovers THAT OFFENSE gave up"
(attributed to its opponent, feeding the `allowing` leaderboard) -- the
same three numbers, just grouped two different ways.
"""

from __future__ import annotations

from backend.schemas.dst_trends.dst_trends import DstTrendsResult, DstTrendTeamRow


def _round1(value: float) -> float:
    return round(value, 1)


def _build_leaderboard(totals: dict[str, dict[str, int]]) -> list[DstTrendTeamRow]:
    """Turns a {team: {"games", "sacks", "takeaways"}} accumulator into
    sorted DstTrendTeamRow entries -- ranked by sacks_per_game descending
    (ties broken by total sacks, then takeaways_per_game, then takeaways)
    since "who's getting to the QB most consistently" is the primary read
    this whole feature exists for; takeaways is the secondary signal."""
    rows = [
        DstTrendTeamRow(
            team=team,
            games=t["games"],
            sacks=t["sacks"],
            sacks_per_game=_round1(t["sacks"] / t["games"]) if t["games"] > 0 else 0.0,
            takeaways=t["takeaways"],
            takeaways_per_game=_round1(t["takeaways"] / t["games"]) if t["games"] > 0 else 0.0,
        )
        for team, t in totals.items()
    ]
    rows.sort(key=lambda r: (r.sacks_per_game, r.sacks, r.takeaways_per_game, r.takeaways), reverse=True)
    return rows


def build_dst_trend_leaderboards(
    dst_stat_lines: dict[tuple[str, int], dict[str, int | float | str]],
    season: int,
    week: int,
    window_weeks: int = 5,
) -> DstTrendsResult:
    """`dst_stat_lines` is load_weekly_stat_lines's own output run against
    FantasyData_DSTs.csv (one line per (DST name, week), each carrying its
    own "team"/"opponent"/"sacks"/"def_int"/"fumble_recoveries"). Reviews
    `through_week = week - 1` and the `window_weeks - 1` weeks before that
    (clamped to week 1) -- same "always review the most recently completed
    week" convention as Multipliers' own base_week, since a week still in
    progress has incomplete DST stats.

    Empty result (through_week < 1) when `week` is the season's first
    week -- there's nothing to review yet, same edge case Multipliers'
    own noPriorWeek handles on the frontend."""
    through_week = week - 1
    if through_week < 1:
        return DstTrendsResult(season=season, week=week, through_week=through_week, window_weeks=window_weeks, forcing=[], allowing=[])

    min_week = max(1, through_week - window_weeks + 1)

    forcing_totals: dict[str, dict[str, int]] = {}
    allowing_totals: dict[str, dict[str, int]] = {}

    for (_name, line_week), stat_line in dst_stat_lines.items():
        if line_week < min_week or line_week > through_week:
            continue
        team = str(stat_line.get("team") or "").strip()
        opponent = str(stat_line.get("opponent") or "").strip()
        sacks = int(stat_line.get("sacks", 0))
        takeaways = int(stat_line.get("def_int", 0)) + int(stat_line.get("fumble_recoveries", 0))

        if team:
            entry = forcing_totals.setdefault(team, {"games": 0, "sacks": 0, "takeaways": 0})
            entry["games"] += 1
            entry["sacks"] += sacks
            entry["takeaways"] += takeaways

        if opponent:
            entry = allowing_totals.setdefault(opponent, {"games": 0, "sacks": 0, "takeaways": 0})
            entry["games"] += 1
            entry["sacks"] += sacks
            entry["takeaways"] += takeaways

    return DstTrendsResult(
        season=season,
        week=week,
        through_week=through_week,
        window_weeks=window_weeks,
        forcing=_build_leaderboard(forcing_totals),
        allowing=_build_leaderboard(allowing_totals),
    )
