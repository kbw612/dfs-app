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

save_entry does its read-modify-write through
backend/repositories/atomic_json.py's locked_read_modify_write rather than
a plain read + path.write_text -- this file is now written to several
times in quick succession whenever Game Matchup's team+position
propagation fires (see PlayerPoolView.tsx's teammateKeysSharingMatchup),
and a naive concurrent read-modify-write on the same file can both lose
one of the updates and, worse, corrupt the file outright if two writes
interleave at the OS level. See atomic_json.py's own docstring for the
exact failure this is guarding against -- it happened for real to
data/nfl/2026/dk_player_factors_week1.json before this fix.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.repositories.atomic_json import locked_read_modify_write
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
    path = _path(nfl_data_dir, entry.season, entry.week, entry.platform)

    def modify(data: dict) -> None:
        data[entry.player] = entry.model_dump(exclude={"season", "week", "platform", "player"})

    locked_read_modify_write(
        path, lambda: _load_raw(nfl_data_dir, entry.season, entry.week, entry.platform), modify
    )


def save_ownership_scores(nfl_data_dir: Path, season: int, week: int, platform: str, scores: dict[str, float]) -> None:
    """Bulk-applies fresh Ownership scores (see backend/services/
    ownership/scoring.py's score_ownership_pct, used by the Player
    Rankings refresh icon -- backend/api/player_pool/
    calculate_ownership_scores.py) to potentially many players in a
    single locked read-modify-write, rather than one save_entry() call
    per player -- both for efficiency and because save_entry's full-entry
    replace would otherwise require re-reading and re-sending every
    player's other already-saved fields just to touch this one. Unlike
    save_entry, this only ever touches the `ownership` key -- every other
    already-saved field for a player is left exactly as it was (or unset,
    for a player with no entry yet at all)."""
    path = _path(nfl_data_dir, season, week, platform)

    def modify(data: dict) -> None:
        for player, score in scores.items():
            existing = data.get(player, {})
            data[player] = {**existing, "ownership": score}

    locked_read_modify_write(path, lambda: _load_raw(nfl_data_dir, season, week, platform), modify)


def save_weather_scores(nfl_data_dir: Path, season: int, week: int, platform: str, scores: dict[str, float]) -> None:
    """Bulk-applies fresh Weather scores (see backend/services/weather/
    scoring.py's score_weather_color, used by the Player Rankings DST
    Weather refresh icon -- backend/api/player_pool/
    calculate_weather_scores.py) to potentially many DST rows in a single
    locked read-modify-write, same shape as save_ownership_scores above --
    only ever touches the `weather` key, leaving every other already-saved
    field for a player exactly as it was."""
    path = _path(nfl_data_dir, season, week, platform)

    def modify(data: dict) -> None:
        for player, score in scores.items():
            existing = data.get(player, {})
            data[player] = {**existing, "weather": score}

    locked_read_modify_write(path, lambda: _load_raw(nfl_data_dir, season, week, platform), modify)


def clear_game_matchup_overrides(
    nfl_data_dir: Path, season: int, week: int, platform: str, players: set[str] | None = None
) -> list[str]:
    """Removes this week's explicit Matchup override (if any) for every
    player who has one, leaving every other already-saved field (Volume,
    Talent, Ownership, the Game Environment override, Salary Value)
    untouched -- same "only touch the one key this operation is about"
    contract as save_ownership_scores above, just clearing instead of
    setting. Once cleared, that player's Matchup goes back to being
    resolved purely from the fallback chain (see services/player_pool/
    engine.py's _resolve_team_factor_default): the opponent's own Team
    Default Factor at this player's position, or the flat 2.0 neutral if
    that's never been set either -- exactly as if this player had never
    been explicitly scored on Matchup this week at all.

    `players`, when given, narrows this to only that set of player names
    (e.g. just this week's DSTs, for Player Rankings' DST-only Matchup
    refresh icon -- see api/player_pool/reset_matchup.py) -- every other
    player's Matchup override is left alone even if they have one. None
    (the default) keeps the original "clear everyone" behavior, used by
    the one-off admin reset script.

    Returns the list of players whose entry actually had a game_matchup
    key removed (for the caller to report what changed) -- a player with
    no entry, an entry with no game_matchup key already, or a player not
    in `players` (when given) isn't touched or included."""
    path = _path(nfl_data_dir, season, week, platform)
    cleared: list[str] = []

    def modify(data: dict) -> None:
        for player, fields in data.items():
            if players is not None and player not in players:
                continue
            # fields.get(...) is not None (rather than a plain "in fields"
            # membership check) since a full save_entry() replace writes
            # every field via model_dump(), including an explicit
            # "game_matchup": null for a player who was never actually
            # scored on Matchup that week (see this module's own
            # docstring) -- that's not a real override to clear, so it
            # shouldn't count as one.
            if fields.get("game_matchup") is not None:
                del fields["game_matchup"]
                cleared.append(player)

    locked_read_modify_write(path, lambda: _load_raw(nfl_data_dir, season, week, platform), modify)
    return cleared


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
