"""
Persists the global Name Aliases list (backend/schemas/name_aliases/
name_aliases.py) as a single JSON file (settings.name_aliases_json) --
not scoped to season/week/platform at all, since a name mismatch between
DK's own exports and a third-party stat site isn't specific to one season.
Saving always replaces the whole list -- the caller sends the complete
current set, not a partial patch, same convention as player_defaults'
save_default for an individual entry.

Shape on disk:

    {"aliases": [{"alias": "James Cook III", "canonical": "James Cook"}]}
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.name_aliases.name_aliases import NameAlias


def load_name_aliases(name_aliases_json: Path) -> list[NameAlias]:
    if not name_aliases_json.exists():
        return []
    data = json.loads(name_aliases_json.read_text(encoding="utf-8"))
    return [NameAlias(**row) for row in data.get("aliases", [])]


def save_name_aliases(name_aliases_json: Path, aliases: list[NameAlias]) -> None:
    name_aliases_json.parent.mkdir(parents=True, exist_ok=True)
    data = {"aliases": [alias.model_dump() for alias in aliases]}
    name_aliases_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
