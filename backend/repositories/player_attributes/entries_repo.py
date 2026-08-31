"""
Persists Player Attribute entries (backend/schemas/player_attributes/
player_attributes.py's PlayerAttributeEntry) -- one JSON file per season,
same reasoning as Player Pool's own entries_repo.py: the carry-forward
behavior for Volume/Talent needs to look back across every earlier week in
the same season to find a player's most recently-scored value, and keeping
a season's weeks together in one file makes that a dict lookup instead of
a directory scan.

Shape on disk (data/player_attributes/entries_{season}.json):

    {
      "season": 2025,
      "weeks": {
        "9": {"Josh Allen": {"volume": 2.0, "talent": 3.0}, ...},
        "10": {...}
      }
    }

Each per-player dict under a week is exactly PlayerAttributeEntry's fields
minus season/week/player. Saving a player's entry for a week fully replaces
whatever was there before for that (week, player).
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.player_attributes.player_attributes import PlayerAttributeEntry

_FILENAME_PREFIX = "entries_"

_ENTRY_FIELDS = ["volume", "talent"]


def _path(player_attributes_dir: Path, season: int) -> Path:
    return player_attributes_dir / f"{_FILENAME_PREFIX}{season}.json"


def _load_raw(player_attributes_dir: Path, season: int) -> dict:
    path = _path(player_attributes_dir, season)
    if not path.exists():
        return {"season": season, "weeks": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_raw(player_attributes_dir: Path, season: int, data: dict) -> None:
    player_attributes_dir.mkdir(parents=True, exist_ok=True)
    _path(player_attributes_dir, season).write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_entry(player_attributes_dir: Path, entry: PlayerAttributeEntry) -> None:
    data = _load_raw(player_attributes_dir, entry.season)
    week_key = str(entry.week)
    data.setdefault("weeks", {}).setdefault(week_key, {})
    data["weeks"][week_key][entry.player] = entry.model_dump(exclude={"season", "week", "player"})
    _save_raw(player_attributes_dir, entry.season, data)


def load_entry(player_attributes_dir: Path, season: int, week: int, player: str) -> PlayerAttributeEntry | None:
    """The entry actually saved for this exact week, or None if this
    player hasn't been scored yet in this exact week (see
    resolve_carry_forward_value for looking further back)."""
    data = _load_raw(player_attributes_dir, season)
    fields = data.get("weeks", {}).get(str(week), {}).get(player)
    if fields is None:
        return None
    return PlayerAttributeEntry(season=season, week=week, player=player, **fields)


def load_entries_for_week(player_attributes_dir: Path, season: int, week: int) -> dict[str, PlayerAttributeEntry]:
    """{player_name: PlayerAttributeEntry} for every player explicitly
    scored in this exact week."""
    data = _load_raw(player_attributes_dir, season)
    week_data = data.get("weeks", {}).get(str(week), {})
    return {
        player: PlayerAttributeEntry(season=season, week=week, player=player, **fields)
        for player, fields in week_data.items()
    }


def resolve_carry_forward_value(player_attributes_dir: Path, season: int, week: int, player: str, field: str) -> float | None:
    """The most recent non-None value for `field` from any week strictly
    before `week` this season, walking backwards from week-1 -- e.g. if
    Volume was set to 3 in week 8, never touched in weeks 9-10, this
    returns 3 for both. Returns None if the player has no earlier score
    for this field (including if they've never been scored at all)."""
    if field not in _ENTRY_FIELDS:
        raise ValueError(f"Unknown Player Attribute field '{field}' -- choose one of {_ENTRY_FIELDS}.")

    data = _load_raw(player_attributes_dir, season)
    weeks = data.get("weeks", {})
    earlier_weeks = sorted((int(w) for w in weeks if int(w) < week), reverse=True)
    for earlier_week in earlier_weeks:
        player_fields = weeks[str(earlier_week)].get(player)
        if player_fields is not None and player_fields.get(field) is not None:
            return player_fields[field]
    return None
