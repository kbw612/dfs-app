"""
GET /game-logs-summary?season=&week=&window_weeks=&platform=&contest=
(mounted at /api/game-logs-summary). Backs the Game Logs Summary tab: slate-
wide roll-ups over the last `window_weeks` completed weeks -- the QB
passing-yards panel (qb_passing.py) and the RB rushing-yards panel
(rb_rushing.py), both under backend/services/game_logs_summary/.

Needs only the QB and RB weekly stats files and the Schedule file. Both degrade
gracefully rather than 404ing: no QB file means `qb_passing` is None, and no
Schedule file just means no home/away markers and no QB gets a row (rows are
this week's matchups). `contest` narrows QBs and defenses to the selected
contest's own DK salary slate, same contest_teams derivation as Game
Previews/Game Logs; no salary file uploaded yet leaves the slate unscoped.
The depth-chart snapshot is optional and only supplies QB injury status.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.repositories.dk_players.weekly_stats_repo import load_weekly_stats_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.schemas.game_logs_summary.game_logs_summary import GameLogsSummaryResult
from backend.services.dk_players.weekly_stats_loader import load_weekly_stat_lines
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.game_logs_summary.qb_passing import build_qb_passing
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv
from backend.services.game_logs.game_logs_engine import build_game_options
from backend.services.game_logs_summary.position_multipliers import build_position_multipliers
from backend.services.game_logs_summary.rb_receiving import build_rb_receiving
from backend.services.game_logs_summary.rb_rushing import build_rb_rushing
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


@router.get("/game-logs-summary", response_model=GameLogsSummaryResult)
def game_logs_summary_endpoint(
    season: int, week: int, window_weeks: int = 5, platform: str = "DraftKings", contest: str = "Classic Main"
) -> GameLogsSummaryResult:
    schedule_csv = load_schedule_csv(settings.nfl_data_dir, season)
    schedule_rows = parse_schedule_csv(schedule_csv) if schedule_csv is not None else []

    contest_teams: set[str] | None = None
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is not None:
        salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        contest_teams = {p.team for p in salary_snapshot.players}

    qb_csv = load_weekly_stats_csv(settings.nfl_data_dir, season, "QB")
    qb_stat_lines = load_weekly_stat_lines(qb_csv) if qb_csv is not None else {}

    rb_csv = load_weekly_stats_csv(settings.nfl_data_dir, season, "RB")
    rb_stat_lines = load_weekly_stat_lines(rb_csv) if rb_csv is not None else {}

    tracker_csv = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    tracker_rows = parse_dk_players_csv(tracker_csv) if tracker_csv is not None else []

    snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    depth_chart_snapshot = load_snapshot(snapshot_path) if snapshot_path is not None else None

    return GameLogsSummaryResult(
        season=season,
        week=week,
        window_weeks=window_weeks,
        games=build_game_options(schedule_rows, week, contest_teams),
        contest_salary_file_missing=contest_teams is None,
        qb_passing=build_qb_passing(
            qb_stat_lines,
            schedule_rows,
            week,
            window_weeks,
            contest_teams=contest_teams,
            depth_chart_snapshot=depth_chart_snapshot,
        ),
        rb_rushing=build_rb_rushing(
            rb_stat_lines,
            schedule_rows,
            week,
            window_weeks,
            contest_teams=contest_teams,
            depth_chart_snapshot=depth_chart_snapshot,
        ),
        rb_receiving=build_rb_receiving(
            rb_stat_lines,
            schedule_rows,
            week,
            window_weeks,
            contest_teams=contest_teams,
            depth_chart_snapshot=depth_chart_snapshot,
        ),
        **{
            f"{pos.lower()}_multipliers": build_position_multipliers(
                tracker_rows,
                schedule_rows,
                week,
                window_weeks,
                contest_teams=contest_teams,
                depth_chart_snapshot=depth_chart_snapshot,
                position=pos,
            )
            for pos in ("QB", "RB", "WR", "TE")
        },
    )
