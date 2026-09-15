"""
Loads data/nfl/2026/settings/usage_bump_position_settings.json (see
backend/config.py's usage_bump_position_settings_json) -- the universal (not
per-team) fallback used when an out player has no entry in
usage_bump_players.json. Keyed by role label ("RB1" = the real rank-1
running back on whatever team is being evaluated, not a specific named
player), so the same entry applies across every team.

Sparse by design, same as usage_bump_players.json -- a role with no entry
here (and no curated override) simply produces zero bump when that role
is out. There's no third fallback.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_usage_bump_position_settings(json_path: Path) -> dict[str, list[str]]:
    """{out_position_label: [usage_bump_position_label, ...]} in priority
    order -- e.g. {"RB1": ["RB2", "RB3", "WR1", "WR2", "TE1", "WR3"]}.
    Empty dict if the file doesn't exist yet."""
    if not json_path.exists():
        return {}

    data = json.loads(json_path.read_text(encoding="utf-8"))
    settings: dict[str, list[str]] = {}
    for entry in data.get("settings", []):
        out_position = entry.get("outPosition")
        if not out_position:
            continue
        settings[out_position] = entry.get("usageBumpPositions", [])
    return settings
