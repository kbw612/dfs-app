"""
Field-level parsing shared by every way ownership data can get into this
app -- the live scraper (scraper.py) and the CSV importer (csv_loader.py)
both need the exact same salary/ownership/team/opponent parsing, so it
lives here once rather than being duplicated (and drifting) between them.
"""

from __future__ import annotations

import re

# oneweekseason.com renders LA's two teams inconsistently on its ownership
# page (seen in the wild: "LA" for the Rams, "LARC" for the Chargers) --
# real quirks in the source site's markup, not something a canonical
# abbreviation lookup (config/team-info.csv) can resolve on its own since
# "LA" alone is ambiguous between the two LA teams. The same quirk shows up
# in the CSV export of that page, so both scraper.py and csv_loader.py need
# this fix.
TEAM_ABBREV_FIXES = {
    "LARC": "LAC",
    "LA": "LAR",
}


def normalize_team_abbrev(raw: str) -> str:
    raw = raw.strip()
    return TEAM_ABBREV_FIXES.get(raw, raw)


def parse_opponent(raw: str) -> tuple[str, bool]:
    """"@HOU" -> ("HOU", False) [this team is away]; "ARI" -> ("ARI",
    True) [this team is home]."""
    raw = raw.strip()
    is_home = not raw.startswith("@")
    return normalize_team_abbrev(raw.lstrip("@")), is_home


def parse_salary(raw: str) -> int:
    # "$5,600" -> 5600
    return int(re.sub(r"[^\d]", "", raw))


def parse_ownership_pct(raw: str) -> float:
    # "30.5%" -> 30.5
    return float(raw.strip().rstrip("%"))
