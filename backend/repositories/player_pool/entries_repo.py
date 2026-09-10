"""
Persists Player Pool score entries (backend/schemas/player_pool/
player_pool.py's PlayerPoolEntry) -- one JSON file per (season, week,
platform), same layout as dk_salary/player_selection (see
backend/config.py's nfl_data_dir and backend/services/platform_settings/
prefix.py for the filename prefix). None of Player Pool's own fields carry
forward from an earlier week (Game Matchup, Ownership, Salary Value, the
Game Environment override, and Volume/Talent too) -- every week's entry is
independent. Volume/Talent's *fallback* when a week has no explicit save
comes from the separate Player Defaults resource instead (see
backend/repositories/player_defaults/defaults_repo.py and
services/player_pool/engine.py's compute_player_pool) -- that's a
different, season-scoped (not per-week) concept from this file's entries.

Shape on disk (data/nfl/{season}/{prefix}_player_factors_week{week}.json):

    {"Josh Allen": {"ownership": 3.0, "game_matchup": 2.0, "volume": 2.0, ...}, ...}

Each per-player dict is exactly PlayerPoolEntry's fields minus
season/week/platform/player (those four are implied by where the entry
lives -- the file's own path plus the dict key). Saving a player's entry
fully replaces whatever was there before for that (week, player) -- the
caller (the API layer) always sends the complete current set of fields
from the edit form, not a partial patch, so there's no merge logic needed
here.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.player_pool.player_pool import PlayerPoolEntry
from backend.services.platform_settings.prefix import platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str) -> Path:
    prefix = platform_file_prefix(platform)
    return nfl_data_dir / str(season) / f"{prefix}_player_factors_week{week}.json"


def _load_raw(nfl_data_dir: Path, season: int, week: int, platform: str) -> dict:
    path = _path(nfl_data_dir, season, week, platform)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_entry(nfl_data_dir: Path, entry: PlayerPoolEntry) -> None:
    data = _load_raw(nfl_data_dir, entry.season, entry.week, entry.platform)
    data[entry.player] = entry.model_dump(exclude={"season", "week", "platform", "player"})
    path = _path(nfl_data_dir, entry.season, entry.week, entry.platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_entry(nfl_data_dir: Path, season: int, week: int, platform: str, player: str) -> PlayerPoolEntry | None:
    """The entry actually saved for this exact (week, platform), or None
    if this player hasn't been scored yet -- none of Player Pool's own
    fields carry forward (see this module's docstring), so there's no
    "look further back" fallback here."""
    data = _load_raw(nfl_data_dir, season, week, platform)
    fields = data.get(player)
    if fields is None:
        return None
    return PlayerPoolEntry(season=season, week=week, platform=platform, player=player, **fields)


def load_entries_for_week(nfl_data_dir: Path, season: int, week: int, platform: str) -> dict[str, PlayerPoolEntry]:
    """{player_name: PlayerPoolEntry} for every player explicitly scored
    in this exact (week, platform)."""
    data = _load_raw(nfl_data_dir, season, week, platform)
    return {
        player: PlayerPoolEntry(season=season, week=week, platform=platform, player=player, **fields)
        for player, fields in data.items()
    }
