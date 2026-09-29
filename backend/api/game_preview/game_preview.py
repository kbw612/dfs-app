"""
GET /game-preview?season=&week=&window_weeks=&platform=&contest= (mounted
at /api/game-preview -- see backend/api/game_preview/__init__.py). Backs
the Game Preview tab's full Phase A + Phase B + Phase D pipeline --
team-level matchup context (Vegas/Weather/Team Factors/DST matchup), per-
player Play/Fade/Monitor/Leverage/Chalk tags, and per-team injury summary
bullets (see backend/services/game_preview/game_preview_engine.py's own
docstring for the Phase A/B/C/D split).

404 only when the Schedule file hasn't been uploaded for this season at
all -- without it there's no way to even know which games exist this week
(same "nothing to show at all" reasoning as every other tab's own hard-
failure case). Every other input (Vegas Lines, Weather, DST weekly stats,
Team Default Factors, DK Players tracker, per-position weekly stat lines,
Ownership projections, the depth-chart snapshot backing Usage Bumps/
Phase D, Star Players) degrades gracefully to None/empty per game instead
of 404ing -- see the engine's own per-field docstrings, and (for the
depth-chart snapshot specifically) find_latest_snapshot's own
None-when-none-scraped-yet convention, same "no snapshot yet" graceful
path GET /opportunities/latest also has to handle, just without that
endpoint's own 404 -- a Game Preview caller reasonably wants everything
else on the page even before the first depth-chart scrape has ever run.

`platform` defaults to "DraftKings", same convention as every other
platform-scoped endpoint (Multipliers, Ownership Summary, ...) -- it scopes
the DK Players tracker file and the Ownership projections file, both of
which are saved per (season, platform) or (season, week, platform).

`contest` (defaults to "Classic Main", same default every other
contest-scoped endpoint uses) narrows the Schedule-driven game list down
to just the teams on that contest's own DK salary slate -- same
"derived from that contest's own salary file, None (no narrowing) if it
hasn't been uploaded yet" behavior as game_logs.py's own contest_teams,
reused here via the same games_for_week/opponent_and_location plumbing
(see game_preview_engine.py -- games_for_week already accepts a
contest_teams-style narrowing indirectly through the schedule_rows it's
given, so narrowing happens here at the API layer by filtering
schedule_rows down to contest_teams' own games before they ever reach the
engine)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.repositories.dk_players.weekly_stats_repo import load_weekly_stats_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.ownership.projections_repo import load_projections_csv
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.repositories.star_players.star_players_repo import load_star_players
from backend.repositories.team_factors.team_factors_repo import load_factors_for_season
from backend.repositories.usage_bump.position_settings_repo import load_usage_bump_position_settings
from backend.repositories.usage_bump.scoring_matrix_repo import load_bump_matrix
from backend.repositories.usage_bump.usage_bump_players_repo import load_usage_bump_players
from backend.repositories.vegas_lines.vegas_lines_repo import load_vegas_lines
from backend.repositories.weather.weather_repo import load_weather
from backend.schemas.game_preview.game_preview import GamePreviewResult
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv
from backend.services.dk_players.weekly_stats_loader import load_weekly_stat_lines
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.game_preview.game_preview_engine import build_game_preview
from backend.services.ownership.csv_loader import parse_ownership_projections_csv
from backend.services.schedule.schedule_loader import parse_schedule_csv
from backend.services.usage_bump.engine import compute_usage_bumps

router = APIRouter()

_SHARE_STAT_POSITIONS = ("QB", "RB", "WR", "TE")


@router.get("/game-preview", response_model=GamePreviewResult)
def game_preview_endpoint(
    season: int, week: int, window_weeks: int = 5, platform: str = "DraftKings", contest: str = "Classic Main"
) -> GamePreviewResult:
    schedule_csv = load_schedule_csv(settings.nfl_data_dir, season)
    if schedule_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Schedule file uploaded yet for season {season} -- "
                "upload one from the Settings tab first."
            ),
        )
    schedule_rows = parse_schedule_csv(schedule_csv)

    # Derived from this contest's own salary file, same "a game is kept
    # only if BOTH its teams are in that set" convention as build_game_
    # options' own contest_teams -- see this module's docstring. Stays
    # None (no narrowing) if that file hasn't been uploaded yet.
    contest_teams: set[str] | None = None
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is not None:
        salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        contest_teams = {p.team for p in salary_snapshot.players}

    dst_csv = load_weekly_stats_csv(settings.nfl_data_dir, season, "DST")
    dst_stat_lines = load_weekly_stat_lines(dst_csv) if dst_csv is not None else {}

    vegas = load_vegas_lines(settings.nfl_data_dir, season, week)
    weather = load_weather(settings.nfl_data_dir, season, week)
    factors_by_team_position = load_factors_for_season(settings.nfl_data_dir, season)

    # -- Phase B inputs -- each degrades to empty rather than 404ing, per
    # this module's own docstring.
    tracker_csv = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    tracker_rows = parse_dk_players_csv(tracker_csv) if tracker_csv is not None else []

    stat_lines_by_position: dict[str, dict[tuple[str, int], dict[str, int | float | str]]] = {}
    for position in _SHARE_STAT_POSITIONS:
        position_csv = load_weekly_stats_csv(settings.nfl_data_dir, season, position)
        if position_csv is not None:
            stat_lines_by_position[position] = load_weekly_stat_lines(position_csv)

    ownership_csv = load_projections_csv(settings.nfl_data_dir, season, week, platform)
    ownership_players, _messages = (
        parse_ownership_projections_csv(ownership_csv) if ownership_csv is not None else ([], [])
    )

    usage_bumps = []
    depth_chart_snapshot = None
    snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    if snapshot_path is not None:
        depth_chart_snapshot = load_snapshot(snapshot_path)
        usage_bump_players = load_usage_bump_players(settings.usage_bump_players_json)
        position_settings = load_usage_bump_position_settings(settings.usage_bump_position_settings_json)
        matrix = load_bump_matrix(settings.player_out_settings_json)
        usage_bumps = compute_usage_bumps(depth_chart_snapshot, usage_bump_players, position_settings, matrix)

    # -- Phase D inputs -- star_players is a flat, always-present file (see
    # star_players_repo.py's own docstring: empty StarPlayersResult if
    # nobody's ever starred a player yet, never a missing-file error).
    star_players = load_star_players(settings.star_players_json)

    return build_game_preview(
        season,
        week,
        schedule_rows,
        dst_stat_lines,
        vegas,
        weather,
        factors_by_team_position,
        window_weeks,
        tracker_rows=tracker_rows,
        stat_lines_by_position=stat_lines_by_position,
        ownership_players=ownership_players,
        usage_bumps=usage_bumps,
        depth_chart_snapshot=depth_chart_snapshot,
        star_players=star_players,
        contest_teams=contest_teams,
    )
