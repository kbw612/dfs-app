"""
GET /game-logs-against?season=&week=&platform=&lookback_weeks= (mounted at
/api/game-logs-against -- see backend/api/game_logs_against/__init__.py).
Backs the Game Logs Against tab -- see backend/services/game_logs/
game_logs_against_engine.py for the full computation.

Unlike /api/game-logs, this endpoint IS scoped to the current week's slate:
it computes one "Against {team}" panel per team appearing in this week's
games (same games list build_game_options already returns for Game Logs'
own Game filter), matching the person's own reference script, which only
ever processed the teams in `flat_teams` for the week at hand rather than
all 32 teams league-wide. Selecting a game client-side then just filters
down to that game's two teams' panels -- no separate per-team backend call
needed (see the "Game filter shows both teams" design decision this
endpoint's rows already support via each row's own `against_team` field).

Needs the DK Players tracker + Schedule file, same as before, PLUS the 4
FantasyData weekly stats files (same ones /api/game-logs reads) to
populate each row's Target Share %/Touch Share % and QB passing line --
see game_logs_against_engine.py's own docstring for why those needed a
new data source when the rest of this tab's fields didn't. Same 404
convention as /api/game-logs: no tracker rows at all yet for this
(season, platform) means there's nothing to show. Missing Schedule data
degrades gracefully to an empty `games` list and no rows (every team's
own schedule window is then empty); missing/partial FantasyData files
degrade the same way Game Logs' own do -- that position's share/passing
fields just come back None rather than blocking the rest of the tab.

Also returns `team_stat_summary` -- same team-level Average/Median shape
as /api/game-logs' own (see that endpoint's docstring), just grouped by
`against_team` instead of a rostered player's real team.

`contest` (see /api/game-logs' own docstring) narrows `games`/`teams`
(and therefore which teams get an "Against" panel at all) down to the
currently-selected Contest's own DK salary slate, the same contest_teams
derivation /api/game-logs uses -- a contest whose salary file isn't
uploaded yet for this (season, week, platform) just leaves every
league-wide team's panel showing, unchanged from before this param
existed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv
from backend.repositories.dk_players.weekly_stats_repo import load_weekly_stats_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.name_aliases.name_aliases_repo import load_name_aliases
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.schemas.game_logs.game_logs_against import GameLogsAgainstResult
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv
from backend.services.dk_players.weekly_stats_loader import load_weekly_stat_lines
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.game_logs.game_logs_against_engine import build_game_logs_against_rows
from backend.services.game_logs.game_logs_engine import POSITIONS, build_game_options, build_team_stat_summary
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


@router.get("/game-logs-against", response_model=GameLogsAgainstResult)
def game_logs_against_endpoint(
    season: int, week: int, platform: str = "DraftKings", lookback_weeks: int = 6, contest: str = "Classic Main"
) -> GameLogsAgainstResult:
    tracker_csv = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    if tracker_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No DK Players tracker started yet for season {season} -- "
                'run "Add Week Players" on the DK Players tab first.'
            ),
        )
    tracker_rows = parse_dk_players_csv(tracker_csv)

    schedule_csv = load_schedule_csv(settings.nfl_data_dir, season)
    schedule_rows = parse_schedule_csv(schedule_csv) if schedule_csv is not None else []

    stat_lines_by_position = {}
    for position in POSITIONS:
        stats_csv = load_weekly_stats_csv(settings.nfl_data_dir, season, position)
        stat_lines_by_position[position] = load_weekly_stat_lines(stats_csv) if stats_csv is not None else {}

    name_aliases = {alias.alias: alias.canonical for alias in load_name_aliases(settings.name_aliases_json)}

    contest_teams: set[str] | None = None
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is not None:
        salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        contest_teams = {p.team for p in salary_snapshot.players}

    games = build_game_options(schedule_rows, week, contest_teams)
    teams = sorted({team for game in games for team in game.teams})

    rows = []
    for team in teams:
        rows.extend(
            build_game_logs_against_rows(
                tracker_rows, schedule_rows, team, week, lookback_weeks, stat_lines_by_position, name_aliases
            )
        )

    team_stat_summary = build_team_stat_summary(rows, lambda r: r.against_team)

    return GameLogsAgainstResult(
        season=season,
        week=week,
        lookback_weeks=lookback_weeks,
        games=games,
        rows=rows,
        team_stat_summary=team_stat_summary,
    )
