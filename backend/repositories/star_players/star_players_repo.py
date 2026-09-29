"""
Persists StarPlayersResult (backend/schemas/star_players/star_players.py)
-- one flat, season-wide file at settings.star_players_json (see
backend/config.py), same single-file-no-week-dimension layout as
usage_bump_players.json.

Shape on disk:

    {"players": [{"team": "BAL", "player": "Ronnie Stanley"}, ...]}

set_star_player() only ever touches one (team, player) pair -- add it if
starring, remove it if un-starring -- so the Depth Charts tab's star icon
can save immediately on click without resending the whole list, same
single-key-mutation convention as team_factors_repo.save_factor.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.star_players.star_players import StarPlayerEntry, StarPlayersResult


def load_star_players(json_path: Path) -> StarPlayersResult:
    if not json_path.exists():
        return StarPlayersResult()
    return StarPlayersResult(**json.loads(json_path.read_text(encoding="utf-8")))


def _save(json_path: Path, result: StarPlayersResult) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")


def set_star_player(json_path: Path, team: str, player: str, starred: bool) -> StarPlayersResult:
    """Adds or removes the (team, player) pair and rewrites the file --
    idempotent either way (starring an already-starred player, or
    un-starring one that isn't, both just leave the pair absent/present as
    requested rather than erroring)."""
    current = load_star_players(json_path)
    remaining = [e for e in current.players if not (e.team == team and e.player == player)]
    if starred:
        remaining.append(StarPlayerEntry(team=team, player=player))
    remaining.sort(key=lambda e: (e.team, e.player))
    updated = StarPlayersResult(players=remaining)
    _save(json_path, updated)
    return updated
