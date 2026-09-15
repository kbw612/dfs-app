"""
POST /calculate-week-points?season=&week=&platform= (mounted at
/api/dk-players/calculate-week-points). Combined "step 3+4" of the DK
Players workflow -- see backend/services/dk_players/dk_players_engine.py's
calculate_week_points() docstring for why %Drafted/FPTS/Non_TD_FPTS/
TD_FPTS are one calculation, not separable steps.

Always reads the "All Games" contest's Contest Standings -- same reasoning
as add_week.py's own docstring (DK Players tracks every player on the
week's full slate, and "All Games" is the only contest guaranteed to cover
all of them), regardless of whatever contest happens to be selected in
Settings. 404 if it isn't uploaded yet, since FPTS/%Drafted have no other
source. The 4 FantasyData stat files (QB/RB/WR/TE) are read individually
and any that are simply missing just contribute no TD data (that
position's players show up in the result's missing_stat_files instead of
failing the whole request) -- see backend/repositories/dk_players/
weekly_stats_repo.py.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import load_contest_standings_csv
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv, save_dk_players_csv
from backend.repositories.dk_players.weekly_stats_repo import load_weekly_stats_csv, week_has_data
from backend.repositories.name_aliases.name_aliases_repo import load_name_aliases
from backend.schemas.dk_players.dk_players import CalculateWeekPointsResult
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv, serialize_dk_players_csv
from backend.services.dk_players.dk_players_engine import calculate_week_points
from backend.services.dk_players.weekly_stats_loader import merge_td_points

router = APIRouter()

_POSITIONS = ["QB", "RB", "WR", "TE"]

# DK Players always draws from the "All Games" contest's files -- see this
# module's docstring for why.
_CONTEST = "All Games"


@router.post("/calculate-week-points", response_model=CalculateWeekPointsResult)
def calculate_week_points_endpoint(
    season: int, week: int, platform: str = "DraftKings"
) -> CalculateWeekPointsResult:
    contest_csv = load_contest_standings_csv(settings.nfl_data_dir, season, week, platform, _CONTEST)
    if contest_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No All Games Contest Standings uploaded yet for season {season} week {week} -- upload it in "
                "the Settings tab first (select the All Games contest)."
            ),
        )

    existing_csv = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    existing_rows = parse_dk_players_csv(existing_csv) if existing_csv is not None else []
    if not any(row.week == week for row in existing_rows):
        raise HTTPException(
            status_code=404,
            detail=f"Week {week} has no players in the tracker yet -- run \"Add Week {week} Players\" first.",
        )

    # A position's season file can already exist from an earlier week even
    # though *this* week's rows were never saved to it -- so "missing" has
    # to be judged by week_has_data(), not by whether load_weekly_stats_csv
    # returns something at all (see weekly_stats_repo.py's docstring).
    stats_csvs = {
        position: csv_text
        for position in _POSITIONS
        if week_has_data(settings.nfl_data_dir, season, position, week)
        and (csv_text := load_weekly_stats_csv(settings.nfl_data_dir, season, position)) is not None
    }
    missing_stat_positions = [position for position in _POSITIONS if position not in stats_csvs]
    td_points_by_player = merge_td_points(stats_csvs, week)

    standings = parse_contest_standings_csv(contest_csv)
    name_aliases = {alias.alias: alias.canonical for alias in load_name_aliases(settings.name_aliases_json)}

    updated_rows, result = calculate_week_points(
        existing_rows, week, td_points_by_player, standings.reference_rows, name_aliases, missing_stat_positions
    )
    save_dk_players_csv(settings.nfl_data_dir, season, platform, serialize_dk_players_csv(updated_rows))
    return result
