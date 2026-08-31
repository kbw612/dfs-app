"""
GET /latest?season=&week=&platform= (mounted at /api/player-selection/latest
-- see backend/api/player_selection/__init__.py). Every QB/RB/WR/TE in this
week's salary file (see backend/api/dk_salary/import_csv.py), each with its
computed `selected` state (an explicit override if one's been saved, else
the position/salary default -- see backend/services/player_selection/
engine.py). DST is left out entirely -- this feature doesn't apply to it,
every DST always shows up in Player Pool/Salary Blocks regardless (see
that module's docstring). 404 if no salary file's been uploaded yet.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.player_selection.player_selection_repo import load_overrides
from backend.schemas.player_selection.player_selection import PlayerSelectionResult, PlayerSelectionRow
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.player_selection.engine import resolve_selected

router = APIRouter()


@router.get("/latest", response_model=PlayerSelectionResult)
def player_selection_latest_endpoint(season: int, week: int, platform: str = "DraftKings") -> PlayerSelectionResult:
    try:
        csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=f"No DK salary file uploaded yet for season {season} week {week} -- upload this week's DK salary export first.",
        )
    salary_snapshot, _messages = parse_dk_salary_csv(csv_text, season, week)
    overrides = load_overrides(settings.nfl_data_dir, season, week, platform)

    rows = [
        PlayerSelectionRow(
            player=p.player,
            position=p.position,
            team=p.team,
            salary=p.salary,
            opponent=p.opponent,
            is_home=p.is_home,
            selected=resolve_selected(p.player, p.position, p.salary, overrides),
        )
        for p in salary_snapshot.players
        if p.position != "DST"
    ]
    return PlayerSelectionResult(players=rows)
