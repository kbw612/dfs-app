"""
Persists Team Default Factor entries (backend/schemas/team_factors/
team_factors.py's TeamFactorEntry) -- one JSON file per season, keyed by
team then position. No week dimension, same "season-wide baseline, not a
per-week score" reasoning as backend/repositories/player_defaults/
defaults_repo.py, which this closely mirrors.

Lives under the shared per-season nfl_data_dir layout, same
data/nfl/{season}/settings/ directory Player Default Factors' own
player_factors.json lives in.

Shape on disk (data/nfl/{season}/settings/team_factors.json):

    {
      "season": 2026,
      "factors": {
        "CHI": {"WR": 3.0, "RB": 2.0},
        "SF": {"QB": 1.5},
        ...
      }
    }

Saving a (team, position) entry only ever touches that one nested key --
unlike Player Default Factors (one flat record per player replaced
wholesale), a team can accumulate factors across multiple positions one
save at a time without each save needing to resend every other position's
value too.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.team_factors.team_factors import TeamFactorEntry


def _path(nfl_data_dir: Path, season: int) -> Path:
    return nfl_data_dir / str(season) / "settings" / "team_factors.json"


def _load_raw(nfl_data_dir: Path, season: int) -> dict:
    path = _path(nfl_data_dir, season)
    if not path.exists():
        return {"season": season, "factors": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_raw(nfl_data_dir: Path, season: int, data: dict) -> None:
    path = _path(nfl_data_dir, season)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_factor(nfl_data_dir: Path, entry: TeamFactorEntry) -> None:
    data = _load_raw(nfl_data_dir, entry.season)
    team_factors = data.setdefault("factors", {}).setdefault(entry.team, {})
    if entry.factor is None:
        # Clearing back to "unset" -- drop the key entirely rather than
        # storing a literal null, same tidy-up reasoning as leaving a
        # never-set (team, position) pair out of the file in the first
        # place.
        team_factors.pop(entry.position, None)
    else:
        team_factors[entry.position] = entry.factor
    _save_raw(nfl_data_dir, entry.season, data)


def load_factor(nfl_data_dir: Path, season: int, team: str, position: str) -> TeamFactorEntry | None:
    """This (team, position)'s saved factor for this season, or None if
    it's never been explicitly set."""
    data = _load_raw(nfl_data_dir, season)
    value = data.get("factors", {}).get(team, {}).get(position)
    if value is None:
        return None
    return TeamFactorEntry(season=season, team=team, position=position, factor=value)


def load_factors_for_season(nfl_data_dir: Path, season: int) -> dict[tuple[str, str], TeamFactorEntry]:
    """{(team, position): TeamFactorEntry} for every (team, position) pair
    with a saved factor this season -- the shape backend/services/
    player_pool/engine.py looks up by (opponent, position)."""
    data = _load_raw(nfl_data_dir, season)
    result: dict[tuple[str, str], TeamFactorEntry] = {}
    for team, positions in data.get("factors", {}).items():
        for position, factor in positions.items():
            result[(team, position)] = TeamFactorEntry(season=season, team=team, position=position, factor=factor)
    return result
