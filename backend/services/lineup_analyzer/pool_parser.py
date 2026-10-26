"""
Parses an optimizer export for the Lineup Analyzer: header row of roster
slots ("QB,RB,RB,WR,WR,WR,TE,FLEX,DST"), then one lineup per row, each cell
"Player Name (12345678)". Unlike lineup_scenarios/lineup_upload_parser.py this
keeps the DK player ID (the analyzer joins on it, and a portfolio export needs
it). Cells are returned in the analyzer's canonical slot order (QB, RB, RB,
WR, WR, WR, TE, FLEX, DST) however the file orders its columns.
"""

from __future__ import annotations

import csv
import io
import re

SLOT_ORDER = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
_CELL_RE = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")

# One roster cell: (name, dk_id or "").
Cell = tuple[str, str]


def parse_cell(cell: str) -> Cell:
    match = _CELL_RE.match(cell.strip())
    if match:
        return match.group(1).strip(), match.group(2)
    return cell.strip(), ""


def parse_pool_csv(csv_text: str) -> list[list[Cell]]:
    """Each lineup is 9 cells in SLOT_ORDER. Rows with the wrong width or slot
    counts are skipped. Raises ValueError if the header has no recognizable
    roster slots."""
    rows = [r for r in csv.reader(io.StringIO(csv_text)) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("File has no rows")
    header = [h.strip().upper() for h in rows[0]]
    if sorted(header) != sorted(SLOT_ORDER):
        raise ValueError(f"Expected header slots {','.join(SLOT_ORDER)}; got {','.join(header)}")
    lineups: list[list[Cell]] = []
    for row in rows[1:]:
        if len(row) != len(header):
            continue
        by_slot: dict[str, list[Cell]] = {}
        for slot, cell in zip(header, row):
            by_slot.setdefault(slot, []).append(parse_cell(cell))
        lineups.append([c for slot in ("QB", "RB", "WR", "TE", "FLEX", "DST") for c in by_slot[slot]])
    return lineups


def lineup_key(lineup: list[Cell]) -> frozenset[str]:
    """Identity for de-duplication: the set of players (slot arrangement and
    which RB/WR/TE sits in FLEX do not matter)."""
    return frozenset(i or n for n, i in lineup)
