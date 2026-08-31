"""
Parsing specific to DraftKings' own native salary export ("DKSalaries.csv"
-- the file you download directly from a DK contest), used only by
dk_salary_loader.py. The one thing that format needs and no existing
parser handles is splitting its combined "Game Info" column ("NO@DET
09/13/2026 01:00PM ET") into opponent + home/away for a specific team --
the ownership-projections CSV (backend/services/ownership/parsing.py)
already has team/opponent as separate columns, so it has no equivalent.
"""

from __future__ import annotations

from backend.services.ownership.parsing import normalize_team_abbrev


def parse_game_info(raw: str, team: str) -> tuple[str, bool]:
    """"NO@DET 09/13/2026 01:00PM ET" + team="DET" -> ("NO", True) [DET is
    home]; team="NO" -> ("DET", False) [NO is away]. Only the "AWAY@HOME"
    prefix before the first space matters -- the date/time after it is
    ignored, this app tracks matchups, not kickoff times. Raises
    ValueError if the prefix isn't splittable on "@" or `team` is neither
    side of it, so a malformed/unexpected row gets skipped with a clear
    reason rather than silently mis-assigned."""
    matchup = raw.strip().split(" ", 1)[0]
    if "@" not in matchup:
        raise ValueError(f"Can't parse Game Info {raw!r} -- expected \"AWAY@HOME ...\"")

    away_raw, home_raw = matchup.split("@", 1)
    away, home = normalize_team_abbrev(away_raw), normalize_team_abbrev(home_raw)
    team = normalize_team_abbrev(team)

    if team == home:
        return away, True
    if team == away:
        return home, False
    raise ValueError(f"Team {team!r} isn't playing in matchup {matchup!r}")
