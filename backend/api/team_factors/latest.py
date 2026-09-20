"""
GET /latest?season= (mounted at /api/team-factors/latest -- see
backend/api/team_factors/__init__.py). Every (team, position)'s saved
Team Default Factor for that season -- no week parameter, same
"Defaults aren't a per-week concept" reasoning as GET
/api/player-defaults/latest, which this mirrors. Just echoes whatever's
on disk -- a (team, position) pair that's never been explicitly set
simply isn't in the list, same as a never-set player never appearing in
Player Defaults' own list.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.team_factors.team_factors_repo import load_factors_for_season
from backend.schemas.team_factors.team_factors import TeamFactorEntry

router = APIRouter()


class TeamFactorsLatestResult(BaseModel):
    factors: list[TeamFactorEntry]


@router.get("/latest", response_model=TeamFactorsLatestResult)
def team_factors_latest_endpoint(season: int) -> TeamFactorsLatestResult:
    factors = load_factors_for_season(settings.nfl_data_dir, season)
    return TeamFactorsLatestResult(factors=list(factors.values()))
