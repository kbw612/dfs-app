"""
Persists Player Default entries (backend/schemas/player_defaults/
player_defaults.py's PlayerDefaultEntry) -- one JSON file per season, keyed
by player only. There's no week dimension here at all (unlike Player
Pool's own entries_repo.py) since a Default is a player-level baseline,
not a per-week score -- see the schema module's docstring for how Player
Pool falls back to this when a week has no explicit save of its own.

Lives under the shared per-season nfl_data_dir layout (same root as
dk_salary/player_selection -- see backend/config.py's nfl_data_dir).

Shape on disk (data/nfl/{season}/settings/player_factors.json):

    {
      "season": 2026,
      "defaults": {
        "Josh Allen": {"volume": 2.0, "talent": 3.0, "dfs_types": ["Boom/Bust"]},
        ...
      }
    }

Saving a player's Default fully replaces whatever was there before for
that player -- the caller always sends the complete current set of
fields, not a partial patch.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.player_defaults.player_defaults import PlayerDefaultEntry


def _path(nfl_data_dir: Path, season: int) -> Path:
    return nfl_data_dir / str(season) / "settings" / "player_factors.json"


def _migrate_legacy_dfs_type(fields: dict) -> dict:
    """Pre-multi-tag files saved a single `dfs_type` string (e.g.
    "Boom/Bust") instead of today's `dfs_types` list -- fold that legacy
    value in rather than silently dropping it the first time this record
    is read under the new schema (PlayerDefaultEntry has no `dfs_type`
    field at all anymore, so pydantic would otherwise just ignore the old
    key and the player's existing tag would vanish on next save). Only
    applies when `dfs_types` isn't already present, so a record that's
    already been re-saved under the new shape is left alone."""
    if "dfs_type" not in fields:
        return fields
    migrated = dict(fields)
    legacy_value = migrated.pop("dfs_type")
    if "dfs_types" not in migrated:
        migrated["dfs_types"] = [legacy_value] if legacy_value else []
    return migrated


def _load_raw(nfl_data_dir: Path, season: int) -> dict:
    path = _path(nfl_data_dir, season)
    if not path.exists():
        return {"season": season, "defaults": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_raw(nfl_data_dir: Path, season: int, data: dict) -> None:
    path = _path(nfl_data_dir, season)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_default(nfl_data_dir: Path, entry: PlayerDefaultEntry) -> None:
    data = _load_raw(nfl_data_dir, entry.season)
    data.setdefault("defaults", {})[entry.player] = entry.model_dump(exclude={"season", "player"})
    _save_raw(nfl_data_dir, entry.season, data)


def load_default(nfl_data_dir: Path, season: int, player: str) -> PlayerDefaultEntry | None:
    """This player's saved Default for this season, or None if they've
    never had one set."""
    data = _load_raw(nfl_data_dir, season)
    fields = data.get("defaults", {}).get(player)
    if fields is None:
        return None
    return PlayerDefaultEntry(season=season, player=player, **_migrate_legacy_dfs_type(fields))


def load_defaults_for_season(nfl_data_dir: Path, season: int) -> dict[str, PlayerDefaultEntry]:
    """{player_name: PlayerDefaultEntry} for every player with a saved
    Default this season."""
    data = _load_raw(nfl_data_dir, season)
    return {
        player: PlayerDefaultEntry(season=season, player=player, **_migrate_legacy_dfs_type(fields))
        for player, fields in data.get("defaults", {}).items()
    }
