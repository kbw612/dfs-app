"""
POST /add-week?season=&week=&platform=&confirm_replace=false (mounted at
/api/dk-players/add-week). "Step 1" of the DK Players workflow -- reads
the Salary File already uploaded in Settings for this (season, week,
platform) and appends those players as this week's tracker rows, Salary
filled in and %Drafted/FPTS/Non_TD_FPTS/TD_FPTS all zeroed.

Always reads the "All Games" contest's Salary File (see
backend/services/platform_settings/prefix.py's contest_slug()), never
whichever contest happens to be selected in Settings -- DK Players
is a season-long tracker of every player on the week's full slate, and
"All Games" is the only contest that actually covers all of them (a
single-contest export like "Classic Main" may only include the players
who happened to be rostered in that particular contest). This is
independent of Player Rankings/Salary Blocks, which do follow whatever
contest is currently selected.

If `week` already has rows in the tracker, this refuses with a 409 unless
`confirm_replace=true` is passed -- see backend/services/dk_players/
dk_players_engine.py's week_status/add_week_players_rows. The frontend
should call GET /week-status first to word its own confirm dialog
accurately (e.g. warning specifically when calculated points would be
lost), then retry this call with confirm_replace=true once the person
confirms.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_players.dk_players_repo import load_dk_players_csv, save_dk_players_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.schemas.dk_players.dk_players import AddWeekPlayersResult
from backend.services.dk_players.dk_players_csv import parse_dk_players_csv, serialize_dk_players_csv
from backend.services.dk_players.dk_players_engine import add_week_players_rows, week_status
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv

router = APIRouter()

# DK Players always draws from the "All Games" contest's files -- see this
# module's docstring for why.
_CONTEST = "All Games"


@router.post("/add-week", response_model=AddWeekPlayersResult)
def add_week_endpoint(
    season: int,
    week: int,
    platform: str = "DraftKings",
    confirm_replace: bool = False,
) -> AddWeekPlayersResult:
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, _CONTEST)
    if salary_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No All Games Salary File uploaded yet for season {season} week {week} -- upload it in the "
                "Settings tab first (select the All Games contest)."
            ),
        )

    existing_csv = load_dk_players_csv(settings.nfl_data_dir, season, platform)
    existing_rows = parse_dk_players_csv(existing_csv) if existing_csv is not None else []

    status = week_status(existing_rows, week)
    if status.exists and not confirm_replace:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Week {week} already has {status.player_count} players in the tracker"
                + (" with calculated points" if status.has_calculated_points else "")
                + " -- pass confirm_replace=true to replace them."
            ),
        )

    salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
    new_rows, result = add_week_players_rows(existing_rows, salary_snapshot.players, week)

    save_dk_players_csv(settings.nfl_data_dir, season, platform, serialize_dk_players_csv(new_rows))
    return result
