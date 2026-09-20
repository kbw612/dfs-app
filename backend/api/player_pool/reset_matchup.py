"""
POST /reset-matchup-to-team-factor?season=&week=&platform=&contest=&position=
(mounted at /api/player-pool/reset-matchup-to-team-factor -- see
backend/api/player_pool/__init__.py). Bulk-clears this week's explicit
Matchup override for every player at `position` in this (season, week,
platform, contest)'s DK salary pool, so their Matchup goes back to being
resolved purely from the fallback chain -- the opponent's own Team Default
Factor at this position (Settings' Team Default Factors grid), or the flat
2.0 neutral if that's never been set either (see backend/services/
player_pool/engine.py's _resolve_team_factor_default). "Latest applied
wins," same philosophy as Vegas Lines' bulk apply for Game Environment and
this tab's own Ownership refresh (backend/api/player_pool/
calculate_ownership_scores.py).

Player Rankings only ever wires this up for DST today (its Matchup column's
refresh icon only shows on the DST tab -- see PlayerPoolView.tsx), but
`position` is a plain query param rather than hardcoded so the same
endpoint would work for any other position without a backend change.

404s if no DK salary file has been uploaded yet for this (season, week,
platform, contest) -- same precondition GET /latest depends on.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.player_pool.entries_repo import clear_game_matchup_overrides
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv

router = APIRouter()


class MatchupResetResult(BaseModel):
    season: int
    week: int
    position: str
    reset_count: int


@router.post("/reset-matchup-to-team-factor", response_model=MatchupResetResult)
def reset_matchup_to_team_factor_endpoint(
    season: int, week: int, position: str, platform: str = "DraftKings", contest: str = "Classic Main"
) -> MatchupResetResult:
    try:
        csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No DK salary file uploaded yet for season {season} week {week} -- "
                "upload this week's DK salary export first."
            ),
        )

    salary_snapshot, _messages = parse_dk_salary_csv(csv_text, season, week)
    players_at_position = {p.player for p in salary_snapshot.players if p.position == position}

    cleared = clear_game_matchup_overrides(settings.nfl_data_dir, season, week, platform, players=players_at_position)

    return MatchupResetResult(season=season, week=week, position=position, reset_count=len(cleared))
