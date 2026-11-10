"""
GET /player-signals?season=&week=&platform=&last_weeks=&min_net=&hide_below=&thresholds=&opponent_scope=
(mounted at /api/player-signals). Players come from the Settings-uploaded ownership
projections file (same list and <1% hiding rule as Leverage & Pivots); with no ownership file they
come from the Classic Main DK salary file and `ownership_missing` is true (no ownership values,
so the low-ownership chip and the hide-below filter don't apply); stats come
from the weekly FantasyData files, Vegas lines and the depth-chart snapshot.
`thresholds` is an optional JSON object of overrides -- see
backend/services/player_signals/thresholds.py. Only players whose net signal
count (positive chips minus negative chips) is >= `min_net` are returned.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.repositories.dk_players.weekly_stats_repo import load_weekly_stats_csv
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.ownership.projections_repo import load_projections_csv
from backend.repositories.vegas_lines.vegas_lines_repo import load_vegas_lines
from backend.schemas.player_signals.player_signals import PlayerSignalsResult
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.ownership.csv_loader import parse_ownership_projections_csv
from backend.services.ownership.depth_rank import build_status_lookup
from backend.services.ownership.under_one import DEFAULT_CUTOFF, hide_below_cutoff
from backend.services.player_signals.engine import POSITIONS, Context, build_player_signals, load_rows
from backend.services.player_signals.thresholds import describe, resolve
from backend.services.shared.name_match import normalize_player_name

router = APIRouter()


@router.get("/player-signals", response_model=PlayerSignalsResult)
def player_signals_endpoint(
    season: int,
    week: int,
    platform: str = "DraftKings",
    last_weeks: int = 5,
    min_net: int = 3,
    hide_below: float = DEFAULT_CUTOFF,
    thresholds: str | None = None,
    opponent_scope: str = "last",
) -> PlayerSignalsResult:
    if opponent_scope not in ("last", "season"):
        raise HTTPException(status_code=400, detail="opponent_scope must be 'last' or 'season'")
    if last_weeks < 1:
        raise HTTPException(status_code=400, detail="last_weeks must be at least 1")
    try:
        overrides = json.loads(thresholds) if thresholds else {}
        if not isinstance(overrides, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="thresholds must be a JSON object") from exc
    try:
        csv_text = load_projections_csv(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ownership_missing = csv_text is None
    if csv_text is not None:
        raw_players, _messages = parse_ownership_projections_csv(csv_text)
        players = hide_below_cutoff(raw_players, hide_below)
    else:
        # No ownership file yet: fall back to the DK salary file for the player list, so
        # every signal that doesn't need ownership still shows.
        salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, "Classic Main")
        if salary_csv is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No ownership projections or DK salary file uploaded yet for season {season} week {week} -- "
                    "upload one in the Settings tab."
                ),
            )
        snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        players = list(snapshot.players)

    snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    statuses = build_status_lookup(load_snapshot(snapshot_path) if snapshot_path else None)
    players = [p.model_copy(update={"status": statuses.get(normalize_player_name(p.player))}) for p in players]

    rows_by_pos = {pos: load_rows(load_weekly_stats_csv(settings.nfl_data_dir, season, pos), pos) for pos in POSITIONS}
    values = resolve({k: v for k, v in overrides.items() if isinstance(v, (int, float))})
    ctx = Context(rows_by_pos, load_vegas_lines(settings.nfl_data_dir, season, week), statuses, week, last_weeks, values, opponent_scope)
    everyone = build_player_signals(players, ctx)
    shown = [s for s in everyone if s.net >= min_net]
    return PlayerSignalsResult(
        season=season,
        week=week,
        last_weeks=last_weeks,
        min_net=min_net,
        opponent_scope=opponent_scope,
        ownership_missing=ownership_missing,
        first_week=ctx.first_week,
        through_week=ctx.last_week,
        total_players=len(everyone),
        players=shown,
        thresholds=describe(values),
    )
