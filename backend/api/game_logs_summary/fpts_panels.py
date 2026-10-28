"""
GET /game-logs-summary/fpts (mounted at /api/game-logs-summary/fpts) -- the
five FPTS panels (QB, RB, WR, TE, DST) of the Game Logs Summary tab, finished
for display. Same slate scoping, window and contest handling as the main
summary endpoint; `game` (a game key from that endpoint's `games`) and `team`
(repeatable) are the tab's Game / Team chips, applied here so the frontend only
shows what it receives.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.repositories.dk_players.weekly_stats_repo import load_weekly_stats_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.schemas.game_logs_summary.game_logs_summary import FptsPanelsResult
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv
from backend.services.dk_players.weekly_stats_loader import load_weekly_stat_lines
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.game_logs.game_logs_engine import build_game_options
from backend.services.game_logs_summary.position_fpts import build_position_fpts
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


@router.get("/game-logs-summary/fpts", response_model=FptsPanelsResult)
def fpts_panels_endpoint(
    season: int,
    week: int,
    window_weeks: int = 5,
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    game: str | None = None,
    team: list[str] = Query(default=[]),
) -> FptsPanelsResult:
    schedule_csv = load_schedule_csv(settings.nfl_data_dir, season)
    schedule_rows = parse_schedule_csv(schedule_csv) if schedule_csv is not None else []

    contest_teams: set[str] | None = None
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is not None:
        snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        contest_teams = {p.team for p in snapshot.players}

    tracker_csv = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    tracker_rows = parse_dk_players_csv(tracker_csv) if tracker_csv is not None else []

    stat_lines_by_position = {}
    for pos in ("QB", "RB", "WR", "TE", "DST"):  # the panels with detail lines under each game
        stats_csv = load_weekly_stats_csv(settings.nfl_data_dir, season, pos)
        stat_lines_by_position[pos] = load_weekly_stat_lines(stats_csv) if stats_csv is not None else {}

    snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    depth_chart_snapshot = load_snapshot(snapshot_path) if snapshot_path is not None else None

    # Game chip keeps that matchup's two teams; Team chips narrow further.
    team_filter: set[str] | None = None
    if game:
        match = next((g for g in build_game_options(schedule_rows, week, contest_teams) if g.key == game), None)
        team_filter = set(match.teams) if match else set()
    if team:
        team_filter = set(team) if team_filter is None else team_filter & set(team)

    return FptsPanelsResult(
        **{
            pos.lower(): build_position_fpts(
                tracker_rows,
                schedule_rows,
                week,
                window_weeks,
                contest_teams=contest_teams,
                depth_chart_snapshot=depth_chart_snapshot,
                position=pos,
                team_filter=team_filter,
                stat_lines=stat_lines_by_position.get(pos),
            )
            for pos in ("QB", "RB", "WR", "TE", "DST")
        }
    )
