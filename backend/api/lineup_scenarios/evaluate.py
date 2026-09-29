"""
POST /evaluate?season=&week=&platform=&contest=&min_stack_size= (mounted
at /api/lineup-scenarios/evaluate -- see backend/api/lineup_scenarios/
__init__.py). Body is {"scenarios": [{"label": str, "team_flags":
[{"team": str, "role": str, "positions": [str]}]}]} -- see
backend/schemas/lineup_scenarios/lineup_scenarios.py's LineupScenarioTeamFlag
and ScenarioRole for the exact role values and what `positions` filters.

Loads the lineup batch already saved via POST /upload plus the week's DK
salary snapshot (for team resolution by player name -- see
backend/services/lineup_scenarios/team_resolution.py's docstring for why
that's the only option here), resolves every uploaded player's team,
position, and depth-chart slot (e.g. "RB1"), and scores every
caller-supplied scenario against every lineup (see
lineup_scenario_engine.py's evaluate_scenarios for the exact satisfaction
rule). `min_stack_size` defaults to 1 -- "this team just needs to show up
at all" is a reasonable default scenario, same spirit as every other
optional-threshold param elsewhere in this app.

Unlike the DK salary snapshot (a hard 404 if missing -- team resolution is
pointless without it), the depth-chart snapshot is optional: if nothing's
been scraped yet, resolve_lineup_teams() is called with depth_snapshot=None
and every player's depth_slot just stays None (see that function's own
docstring), so a caller who only cares about team-level scenarios (empty
`positions` filters) isn't blocked by a depth chart they never asked for.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.lineup_scenarios.lineup_upload_repo import load_lineup_upload_csv
from backend.schemas.lineup_scenarios.lineup_scenarios import LineupScenarioAnalysis, LineupScenarioDefinition
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.lineup_scenarios.lineup_scenario_engine import evaluate_scenarios
from backend.services.lineup_scenarios.lineup_upload_parser import parse_lineup_upload_csv
from backend.services.lineup_scenarios.team_resolution import resolve_lineup_teams

router = APIRouter()


class LineupScenarioEvaluateRequest(BaseModel):
    scenarios: list[LineupScenarioDefinition]


@router.post("/evaluate", response_model=LineupScenarioAnalysis)
def evaluate_lineup_scenarios_endpoint(
    request: LineupScenarioEvaluateRequest,
    season: int,
    week: int,
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    min_stack_size: int = 1,
) -> LineupScenarioAnalysis:
    lineup_csv = load_lineup_upload_csv(settings.nfl_data_dir, season, week, platform, contest)
    if lineup_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No lineup file uploaded yet for season {season} week {week} -- "
                "upload your lineups CSV first."
            ),
        )
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No DK salary file uploaded yet for season {season} week {week} -- "
                "upload this week's DK salary export first so player teams can be resolved."
            ),
        )

    lineups = parse_lineup_upload_csv(lineup_csv)
    salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)

    depth_snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    depth_snapshot = load_snapshot(depth_snapshot_path) if depth_snapshot_path is not None else None

    resolved_lineups, unresolved_names = resolve_lineup_teams(lineups, salary_snapshot.players, depth_snapshot)

    results = evaluate_scenarios(resolved_lineups, request.scenarios, min_stack_size)

    return LineupScenarioAnalysis(
        results=results,
        unresolved_player_names=unresolved_names,
        min_stack_size=min_stack_size,
    )
