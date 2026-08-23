"""
Loads config/player-out-settings.json -- the scoring matrix shared by both
usage-bump-players.json and usage-bump-position-settings.json usage-bump
lists (see engine.py for how the two come together). Each entry says: given
that these particular positions *within a usage-bump list* are also out
(on top of the list's own trigger player, who's always out by definition),
here's the bump each of the list's up-to-5 positions gets.

`player_out_depths: [0]` is a sentinel for "just the trigger is out, no one
else in their usage-bump list is" -- it's the base case, not a real
list-position. Every other entry's `player_out_depths` lists actual
1-indexed positions within the usage-bump list (never including the
trigger itself, which never appears as a scorable target -- it's always
out, so it can never receive credit).

This loader stays a faithful, dumb parser of the file -- it doesn't know
what "0" means. engine.py decides which key to look up.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_bump_matrix(json_path: Path) -> dict[tuple[int, ...], dict[int, float]]:
    """{sorted tuple of player_out_depths: {list_position: bump_value}}.
    Empty dict if the file doesn't exist yet (meaning: no bumps computed
    for anyone, since there'd be no scoring rule to apply)."""
    if not json_path.exists():
        return {}

    data = json.loads(json_path.read_text(encoding="utf-8"))
    matrix: dict[tuple[int, ...], dict[int, float]] = {}
    for entry in data.get("player_out_settings", []):
        depths = tuple(sorted(entry.get("player_out_depths", [])))
        values = {int(k): v for k, v in entry.get("bump_depth_values", {}).items()}
        matrix[depths] = values
    return matrix
