"""
Persists Player Pool score entries (backend/schemas/player_pool/
player_pool.py's PlayerPoolEntry) -- one JSON file per season, same
one-file-per-season layout as backend/repositories/player_attributes/
entries_repo.py, kept for consistency even though Player Pool's own fields
(Game Matchup, Ownership, Salary Value, the Game Environment override)
don't carry forward the way Volume/Talent do -- see that module for the
fields that split out into their own shared resource.

Shape on disk (data/player_pool/entries_{season}.json):

    {
      "season": 2025,
      "weeks": {
        "9": {"Josh Allen": {"ownership": 3.0, "game_matchup": 2.0, ...}, ...},
        "10": {...}
      }
    }

Each per-player dict under a week is exactly PlayerPoolEntry's fields
minus season/week/player (those three are implied by where the entry
lives in the structure). Saving a player's entry for a week fully
replaces whatever was there before for that (week, player) -- the caller
(the API layer) always sends the complete current set of fields from the
edit form, not a partial patch, so there's no merge logic needed here.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.player_pool.player_pool import PlayerPoolEntry

_FILENAME_PREFIX = "entries_"


def _path(player_pool_dir: Path, season: int) -> Path:
    return player_pool_dir / f"{_FILENAME_PREFIX}{season}.json"


def _load_raw(player_pool_dir: Path, season: int) -> dict:
    path = _path(player_pool_dir, season)
    if not path.exists():
        return {"season": season, "weeks": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_raw(player_pool_dir: Path, season: int, data: dict) -> None:
    player_pool_dir.mkdir(parents=True, exist_ok=True)
    _path(player_pool_dir, season).write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_entry(player_pool_dir: Path, entry: PlayerPoolEntry) -> None:
    data = _load_raw(player_pool_dir, entry.season)
    week_key = str(entry.week)
    data.setdefault("weeks", {}).setdefault(week_key, {})
    data["weeks"][week_key][entry.player] = entry.model_dump(exclude={"season", "week", "player"})
    _save_raw(player_pool_dir, entry.season, data)


def load_entry(player_pool_dir: Path, season: int, week: int, player: str) -> PlayerPoolEntry | None:
    """The entry actually saved for this exact week, or None if this
    player hasn't been scored yet in this exact week -- none of Player
    Pool's own fields carry forward (see this module's docstring), so
    there's no "look further back" fallback here."""
    data = _load_raw(player_pool_dir, season)
    fields = data.get("weeks", {}).get(str(week), {}).get(player)
    if fields is None:
        return None
    return PlayerPoolEntry(season=season, week=week, player=player, **fields)


def load_entries_for_week(player_pool_dir: Path, season: int, week: int) -> dict[str, PlayerPoolEntry]:
    """{player_name: PlayerPoolEntry} for every player explicitly scored
    in this exact week."""
    data = _load_raw(player_pool_dir, season)
    week_data = data.get("weeks", {}).get(str(week), {})
    return {player: PlayerPoolEntry(season=season, week=week, player=player, **fields) for player, fields in week_data.items()}
