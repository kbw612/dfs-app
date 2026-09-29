"""
GET /summary?season=&week=&platform=&contest= (mounted at
/api/ownership/summary). Backend-computed team/game ownership rollups for
the Ownership Summary tab -- see backend/services/ownership/
ownership_summary.py's own module docstring for why this exists (a single
shared definition of "combined ownership% for a team/game," also reused by
Game Preview's own team_projected_ownership_pct()) rather than the tab
computing its own Team/Game rollups client-side from the raw player list
(GET /projections, still used by this tab's own Players table).

404 only when there's no ownership projections file at all for this
(season, week, platform) -- same as GET /projections. Contest Standings
and the DK salary file both degrade gracefully instead of 404ing (actual_
total_ownership_pct stays None on every row, away_team/home_team stay
None), same "graceful when optional, hard failure only when there's
nothing to show at all" convention as every other tab in this app -- a
team/game rollup is still useful before either of those has been uploaded.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import load_contest_standings_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.ownership.projections_repo import (
    load_initial_projections_csv,
    load_projections_csv,
)
from backend.schemas.ownership.ownership import OwnershipProjectionsPlayer
from backend.schemas.ownership.ownership_summary import OwnershipSummaryResult
from backend.services.contest_results.contest_results_engine import build_contest_result_rows
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.ownership.csv_loader import parse_ownership_projections_csv
from backend.services.ownership.ownership_summary import compute_game_ownership_rollups, compute_team_ownership_rollups

router = APIRouter()


@router.get("/summary", response_model=OwnershipSummaryResult)
def ownership_summary_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"
) -> OwnershipSummaryResult:
    ownership_csv = load_projections_csv(settings.nfl_data_dir, season, week, platform)
    if ownership_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No ownership projections file uploaded yet for season {season} week {week} -- "
                "upload it in the Settings tab."
            ),
        )
    current_players, _messages = parse_ownership_projections_csv(ownership_csv)

    # Same initial-vs-current merge GET /projections does -- see that
    # module's own docstring for why a lone upload (no separate initial
    # file yet) falls back to the current file's own text as its initial.
    initial_csv_text = load_initial_projections_csv(settings.nfl_data_dir, season, week, platform) or ownership_csv
    initial_players, _messages = parse_ownership_projections_csv(initial_csv_text)
    initial_ownership_by_name = {p.player: p.ownership_pct for p in initial_players}

    players = [
        OwnershipProjectionsPlayer(
            **current_player.model_dump(),
            initial_ownership_pct=initial_ownership_by_name.get(current_player.player),
        )
        for current_player in current_players
    ]

    # -- Actual ownership from Contest Standings -- best-effort, same
    # graceful degradation as every other side-channel input in this app;
    # needs BOTH the standings and the salary file (same requirement GET
    # /player-results itself has), since build_contest_result_rows joins
    # Salary in from the latter.
    actual_by_player: dict[str, float] = {}
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    salary_players = []
    if salary_csv is not None:
        salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        salary_players = salary_snapshot.players

    standings_csv = load_contest_standings_csv(settings.nfl_data_dir, season, week, platform, contest)
    if standings_csv is not None and salary_csv is not None:
        standings = parse_contest_standings_csv(standings_csv)
        result_rows = build_contest_result_rows(standings, salary_players, week)
        for row in result_rows:
            actual_by_player[row.player] = actual_by_player.get(row.player, 0.0) + row.pct_drafted

    # -- Home/away, for the Game rollup's own away_team/home_team --
    # resolved from the same contest's own DK salary file, same "-" when
    # unavailable convention as the tab's own player-list Opp column.
    home_by_team = {p.team: p.is_home for p in salary_players if p.is_home is not None}

    teams = compute_team_ownership_rollups(players, actual_by_player)
    games = compute_game_ownership_rollups(players, home_by_team, actual_by_player)
    return OwnershipSummaryResult(teams=teams, games=games)
