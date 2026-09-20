"""
Loads/saves data/nfl/2026/usage_bump_players.json (see backend/config.py's
usage_bump_players_json) -- a hand-curated file of explicit
"if this player is out, these named players get bumped usage" lists, in
priority order. Real-world usage doesn't always follow depth-chart array
order (committee backfields, route-tree overlap, etc.), so this lets
specific injured players be hand-corrected instead of relying on the
position-role-based default list in position_settings_repo.py.

Expected to be sparse and grow over time -- most players won't have an
entry, and that's a normal, expected state (they just use the default
position-based list instead). A missing file is likewise normal (nothing
curated yet), not an error.

Two read shapes over the same file, for two different callers:

- load_usage_bump_players_file -- the file's own nested shape (team ->
  players -> ordered beneficiary list), used by the Usage Bump Players
  tab's own GET /api/usage-bump-players (backend/api/usage_bump/
  players.py) so the editor can render and re-save it faithfully.
- load_usage_bump_players -- flattened to {(team_abbrev, player_name):
  [beneficiary_name, ...]}, used by the engine (backend/services/
  usage_bump/engine.py), which only ever needs a single trigger's own
  list by (team, name), not the whole nested structure.

Both tolerate a malformed entry (a team with no teamAbbrev, a player with
no name) by silently skipping it rather than raising -- a hand-edited file
with some cruft in it should still load, not 500.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.schemas.usage_bump.usage_bump_players import (
    UsageBumpPlayerEntry,
    UsageBumpPlayersResult,
    UsageBumpTeamEntry,
)


def load_usage_bump_players_file(json_path: Path) -> UsageBumpPlayersResult:
    """The file's own nested shape -- empty `teams` if the file doesn't
    exist yet. See this module's own docstring for the lenient-skip
    behavior shared with load_usage_bump_players below."""
    if not json_path.exists():
        return UsageBumpPlayersResult(teams=[])

    data = json.loads(json_path.read_text(encoding="utf-8"))
    teams: list[UsageBumpTeamEntry] = []
    for team in data.get("teams", []):
        team_abbrev = team.get("teamAbbrev")
        if not team_abbrev:
            continue
        players: list[UsageBumpPlayerEntry] = []
        for player in team.get("players", []):
            name = player.get("name")
            if not name:
                continue
            players.append(UsageBumpPlayerEntry(name=name, moreUsagePlayers=player.get("moreUsagePlayers", [])))
        teams.append(UsageBumpTeamEntry(teamAbbrev=team_abbrev, players=players))
    return UsageBumpPlayersResult(teams=teams)


def save_usage_bump_players_file(json_path: Path, result: UsageBumpPlayersResult) -> None:
    """Whole-file replace -- the caller (the Usage Bump Players tab's Save
    button) sends the complete current set, same convention as
    name_aliases_repo.save_name_aliases."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "teams": [
            {
                "teamAbbrev": team.teamAbbrev,
                "players": [
                    {"name": player.name, "moreUsagePlayers": player.moreUsagePlayers} for player in team.players
                ],
            }
            for team in result.teams
        ]
    }
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_usage_bump_players(json_path: Path) -> dict[tuple[str, str], list[str]]:
    """{(team_abbrev, player_name): [beneficiary_name, ...]} in priority
    order -- the first name is the biggest beneficiary. Empty dict if the
    file doesn't exist yet. Built on load_usage_bump_players_file above so
    the two never drift apart on what counts as a valid entry."""
    result = load_usage_bump_players_file(json_path)
    return {
        (team.teamAbbrev, player.name): player.moreUsagePlayers
        for team in result.teams
        for player in team.players
    }
