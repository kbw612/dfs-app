"""
Persists Game Environment entries (backend/schemas/game_environment/
game_environment.py) -- one JSON file per season, same one-file-per-season
shape as backend/repositories/player_pool/entries_repo.py, for
consistency (no cross-week lookup need here, but there's no benefit to a
different layout either).

Shape on disk (data/game_environment/entries_{season}.json):

    {
      "season": 2025,
      "weeks": {
        "9": {
          "BUF-NO": {"home_team": "BUF", "away_team": "NO", "over_under": 47.5, ...},
          ...
        }
      }
    }
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.game_environment.game_environment import GameEnvironmentEntry

_FILENAME_PREFIX = "entries_"


def _path(game_environment_dir: Path, season: int) -> Path:
    return game_environment_dir / f"{_FILENAME_PREFIX}{season}.json"


def _load_raw(game_environment_dir: Path, season: int) -> dict:
    path = _path(game_environment_dir, season)
    if not path.exists():
        return {"season": season, "weeks": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_raw(game_environment_dir: Path, season: int, data: dict) -> None:
    game_environment_dir.mkdir(parents=True, exist_ok=True)
    _path(game_environment_dir, season).write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_game_environment(game_environment_dir: Path, entry: GameEnvironmentEntry) -> None:
    data = _load_raw(game_environment_dir, entry.season)
    week_key = str(entry.week)
    data.setdefault("weeks", {}).setdefault(week_key, {})
    data["weeks"][week_key][entry.game_key] = entry.model_dump(exclude={"season", "week", "game_key"})
    _save_raw(game_environment_dir, entry.season, data)


def replace_week(game_environment_dir: Path, season: int, week: int, entries: list[GameEnvironmentEntry]) -> None:
    """Wholesale-replaces this week's saved games with `entries` -- used by
    the apply endpoint (backend/api/vegas_lines/apply.py), where "latest
    Vegas Lines wins" rather than merging per-game with whatever was
    saved before (unlike save_game_environment's single-game upsert, used
    by manual edits). Any game not present in `entries` is dropped, not
    left over from a prior apply or edit."""
    data = _load_raw(game_environment_dir, season)
    data.setdefault("weeks", {})[str(week)] = {
        entry.game_key: entry.model_dump(exclude={"season", "week", "game_key"}) for entry in entries
    }
    _save_raw(game_environment_dir, season, data)


def load_game_environment_for_week(game_environment_dir: Path, season: int, week: int) -> dict[str, GameEnvironmentEntry]:
    """{game_key: GameEnvironmentEntry} for every game with saved inputs
    in this exact week -- callers scope this to their own week (there's
    no carry-forward for Game Environment; odds are re-entered fresh each
    week since they're a property of that week's specific matchups)."""
    data = _load_raw(game_environment_dir, season)
    week_data = data.get("weeks", {}).get(str(week), {})
    return {
        game_key: GameEnvironmentEntry(season=season, week=week, game_key=game_key, **fields)
        for game_key, fields in week_data.items()
    }
