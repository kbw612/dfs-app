"""
Team abbreviation -> bare mascot nickname (e.g. "LAC" -> "Chargers").

This exists because DraftKings' own salary export names a DST by its bare
nickname alone (no city) -- see backend/services/dk_players/dk_players_engine.py
and data/nfl/{season}/dk_players.csv, e.g. "Chargers", "Cowboys", "Chiefs" --
while other sources that key a team off its abbreviation (FantasyData's own
weekly-stats "TEAM" column among them) don't carry that nickname at all.
config/team-info.csv only has the abbreviation and the full "City Mascot"
name (e.g. "Los Angeles Chargers"), not the bare mascot alone, so neither
that file nor a live lookup covers this -- hence a small hardcoded table.

Keyed by this app's own canonical abbreviations (config/team-info.csv's
"Team" column), which is also what FantasyData's weekly-stats TEAM column
already uses -- no TEAM_ABBREV_FIXES-style normalization needed for the
DST weekly-stats path specifically, but resolve_team_nickname() upper-cases
its input defensively in case a caller passes a lowercase abbreviation.

See backend/services/vegas_lines/scraper.py's _TEAM_ALIASES for the mirror
image of this table (nickname -> abbreviation, lowercase-keyed, built for a
different site's own nickname spelling) -- that table is module-private and
serves a different site's text, so it isn't reused here rather than kept in
sync by hand for two different lookup directions.
"""

from __future__ import annotations

TEAM_NICKNAME_BY_ABBREV: dict[str, str] = {
    "ARI": "Cardinals",
    "ATL": "Falcons",
    "BAL": "Ravens",
    "BUF": "Bills",
    "CAR": "Panthers",
    "CHI": "Bears",
    "CIN": "Bengals",
    "CLE": "Browns",
    "DAL": "Cowboys",
    "DEN": "Broncos",
    "DET": "Lions",
    "GB": "Packers",
    "HOU": "Texans",
    "IND": "Colts",
    "JAX": "Jaguars",
    "KC": "Chiefs",
    "LAC": "Chargers",
    "LAR": "Rams",
    "LV": "Raiders",
    "MIA": "Dolphins",
    "MIN": "Vikings",
    "NE": "Patriots",
    "NO": "Saints",
    "NYG": "Giants",
    "NYJ": "Jets",
    "PHI": "Eagles",
    "PIT": "Steelers",
    "SEA": "Seahawks",
    "SF": "49ers",
    "TB": "Buccaneers",
    "TEN": "Titans",
    "WAS": "Commanders",
}


def resolve_team_nickname(abbrev: str) -> str | None:
    """The bare mascot nickname for a team abbreviation, or None if the
    abbreviation isn't recognized (callers decide how to handle that --
    the DST weekly-stats scraper surfaces it as a per-row parse warning
    rather than silently dropping the row)."""
    return TEAM_NICKNAME_BY_ABBREV.get(abbrev.strip().upper())
