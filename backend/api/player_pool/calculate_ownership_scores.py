"""
POST /calculate-ownership-scores?season=&week=&platform=&contest= (mounted
at /api/player-pool/calculate-ownership-scores -- see backend/api/
player_pool/__init__.py). Bulk-computes each player's Ownership score from
their current ownership_pct (backend/services/ownership/scoring.py's
score_ownership_pct, same bands as the Ownership popover -- see frontend/
src/components/scoringNotes.ts's OWNERSHIP_NOTES) and saves it as that
(season, week, platform)'s Ownership override for every eligible player,
wholesale-replacing whatever Ownership value was saved before for them --
"latest applied wins," same philosophy as Vegas Lines' own bulk apply for
Game Environment (see backend/api/vegas_lines/apply.py). DST is skipped
(Ownership isn't a field DST uses at all, same scope as compute_player_
pool's _fields_for_position), as is any player with no ownership_pct to
score off of (not in the current Ownership projections upload) -- neither
counts as "applied," both roll into `skipped_count`.

Runs against every player in this (season, week, platform, contest)'s
salary pool, independent of Player Selection's checkboxes -- same
independence Player Default Settings and Boom/Bust already rely on, since
narrowing this to only currently-selected players would leave an
unselected player's Ownership score stale until they're selected.

404s if no Ownership projections have been uploaded yet for this (season,
week, platform) at all (nothing to calculate from) or no DK salary file
exists yet for this (season, week, platform, contest) (no player universe
to iterate) -- the same two preconditions /latest itself depends on.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.player_pool.entries_repo import save_ownership_scores
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.ownership.scoring import score_ownership_pct
from backend.services.player_pool.enrichment import enrich_players_for_week

router = APIRouter()


class OwnershipScoresApplyResult(BaseModel):
    season: int
    week: int
    applied_count: int
    skipped_count: int


@router.post("/calculate-ownership-scores", response_model=OwnershipScoresApplyResult)
def calculate_ownership_scores_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"
) -> OwnershipScoresApplyResult:
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
    players, ownership_retrieved = enrich_players_for_week(
        salary_snapshot.players, season, week, platform, settings.nfl_data_dir
    )
    if not ownership_retrieved:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Ownership projections uploaded yet for season {season} week {week} -- "
                "upload it in the Settings tab first."
            ),
        )

    scores: dict[str, float] = {}
    skipped_count = 0
    for player in players:
        if player.position == "DST":
            skipped_count += 1
            continue
        score = score_ownership_pct(player.ownership_pct)
        if score is None:
            skipped_count += 1
            continue
        scores[player.player] = score

    save_ownership_scores(settings.nfl_data_dir, season, week, platform, scores)

    return OwnershipScoresApplyResult(season=season, week=week, applied_count=len(scores), skipped_count=skipped_count)
