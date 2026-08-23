"""
Loads config/usage-bump-players.json -- a hand-curated file of explicit
"if this player is out, these named players get bumped usage" lists, in
priority order. Real-world usage doesn't always follow depth-chart array
order (committee backfields, route-tree overlap, etc.), so this lets
specific injured players be hand-corrected instead of relying on the
position-role-based default list in position_settings_repo.py.

Expected to be sparse and grow over time -- most players won't have an
entry, and that's a normal, expected state (they just use the default
position-based list instead). A missing file is likewise normal (nothing
curated yet), not an error.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_usage_bump_players(json_path: Path) -> dict[tuple[str, str], list[str]]:
    """{(team_abbrev, player_name): [beneficiary_name, ...]} in priority
    order -- the first name is the biggest beneficiary. Empty dict if the
    file doesn't exist yet."""
    if not json_path.exists():
        return {}

    data = json.loads(json_path.read_text(encoding="utf-8"))
    players: dict[tuple[str, str], list[str]] = {}
    for team in data.get("teams", []):
        team_abbrev = team.get("teamAbbrev")
        if not team_abbrev:
            continue
        for player in team.get("players", []):
            name = player.get("name")
            if not name:
                continue
            players[(team_abbrev, name)] = player.get("moreUsagePlayers", [])
    return players
