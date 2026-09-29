"""
Parses a person's own already-built lineups export from an external
optimizer into UploadedLineup rows -- a completely different file shape
than backend/services/contest_results/contest_standings_parser.py's own
DraftKings contest-standings export (that one's a per-entry finish
report; this one is just "here are N complete lineups I already built,
tell me about them").

Format (confirmed against the real sample file this feature was built
against): the first row is a header of roster position labels --
"QB,RB,RB,WR,WR,WR,TE,FLEX,DST" -- and every subsequent row is one
lineup, one cell per roster slot, each cell "Player Name (12345678)"
where the parenthesized number is a DraftKings player ID this app has no
column for anywhere (see backend/services/lineup_scenarios/
team_resolution.py's docstring for why team resolution has to go by name
alone). DST cells use a full team name string instead of a person's name
(e.g. "Las Vegas Raiders") -- same convention the DK salary snapshot's
own DST rows use (see dk_salary_loader.py), so no special-casing is
needed here; the bare string is carried through as `name` either way and
team_resolution.py's own name-matching handles both cases identically.
"""

from __future__ import annotations

import csv
import io
import re

from backend.schemas.lineup_scenarios.lineup_scenarios import UploadedLineup, UploadedLineupPlayer

# Matches the trailing " (44220222)"-style DK player-ID suffix on every
# cell -- always a space, an open paren, one or more digits, a close
# paren, anchored to the end of the cell so a player name that happens to
# contain parentheses elsewhere (none seen in practice, but not assumed
# impossible) isn't mangled.
_ID_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")


def _strip_id_suffix(cell: str) -> str:
    return _ID_SUFFIX_RE.sub("", cell).strip()


def parse_lineup_upload_csv(csv_text: str) -> list[UploadedLineup]:
    """Skips any row that doesn't have exactly as many cells as the
    header has roster-position columns -- defensive against a stray
    blank line at the end of the file, same spirit as every other CSV
    parser in this app. Raises ValueError if the file has no header row
    at all (nothing to build roster_position labels from)."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("Lineup upload CSV has no rows")

    roster_positions = [cell.strip() for cell in rows[0]]
    lineups: list[UploadedLineup] = []
    for index, row in enumerate(rows[1:], start=1):
        if len(row) != len(roster_positions):
            continue
        players = [
            UploadedLineupPlayer(roster_position=roster_positions[i], name=_strip_id_suffix(cell), team=None)
            for i, cell in enumerate(row)
        ]
        lineups.append(UploadedLineup(index=index, players=players))
    return lineups
