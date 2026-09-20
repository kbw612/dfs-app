"""
PUT /entry (mounted at /api/team-factors/entry -- see
backend/api/team_factors/__init__.py). Body is a full TeamFactorEntry --
Settings' Team Default Factors grid sends this whenever a (team,
position) cell is saved (see team_factors_repo.save_factor: only that one
(team, position) key is touched, every other position's saved factor for
that team is untouched). Distinct from PUT /api/player-pool/entry -- that
one saves a specific week's explicit Matchup value for one player, this
one saves the team-level, season-wide fallback Player Pool's Matchup
field uses when a week has no explicit save of its own (see
backend/services/player_pool/engine.py's compute_player_pool).
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.team_factors.team_factors_repo import save_factor
from backend.schemas.team_factors.team_factors import TeamFactorEntry

router = APIRouter()


@router.put("/entry", response_model=TeamFactorEntry)
def team_factors_save_entry_endpoint(entry: TeamFactorEntry) -> TeamFactorEntry:
    save_factor(settings.nfl_data_dir, entry)
    return entry
