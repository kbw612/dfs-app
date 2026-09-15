"""
Parses DraftKings' own "contest standings" export -- the CSV a contest's
"Export to CSV" button produces, NOT the salary file (see
backend/services/dk_salary/dk_salary_loader.py for that one, a
completely different column shape). This file packs two unrelated tables
side by side into one CSV, aligned only by row position, not any shared
key:

    Rank,EntryId,EntryName,TimeRemaining,Points,Lineup,,Player,Roster Position,%Drafted,FPTS

Columns 0-5 are one row per contest entry -- Lineup is a single
space-separated string of "SLOT Player Name" pairs, always in the fixed
order DST, FLEX, QB, RB, RB, TE, WR, WR, WR (DK's own Classic-contest
roster construction, alphabetical by slot label -- see
parse_lineup_text). Column 6 is a blank spacer column DK's own export
leaves in place between the two tables. Columns 7-10 are a completely
separate table: every distinct (player, roster slot) pairing that
appeared *anywhere* in the contest, sorted by %Drafted descending, with
that slot's own drafted% and the player's actual FPTS.

The two tables are simply different lengths in practice (entry count vs.
distinct player+slot combos) -- whichever runs out first just leaves the
other side's columns blank for the remaining rows. This module parses
each side independently and lets the caller line up whatever it actually
needs (see contest_results_engine.py) rather than assuming any
relationship between a given row's two halves.
"""

from __future__ import annotations

import csv
import io
import re

from pydantic import BaseModel

# Fixed slot-label order a Classic-contest Lineup string always uses --
# alphabetical by slot name (DST, FLEX, QB, RB, RB, TE, WR, WR, WR), which
# happens to also be DK's own roster-construction order (1 DST, 1 FLEX,
# 1 QB, 2 RB, 1 TE, 3 WR). Used as a regex alternation to split the
# combined "SLOT Name SLOT Name ..." string back into (slot, name) pairs
# -- \b word-boundary matching so a token only matches as a standalone
# slot label, never as a substring of a player's own name (none of DST/
# FLEX/QB/RB/TE/WR collide with real player-name substrings anyway, but
# the word boundary is what protects that assumption if they ever did).
_SLOT_TOKEN_RE = re.compile(r"\b(DST|FLEX|QB|RB|TE|WR)\b")

# How many columns the raw file's header always declares (see this
# module's docstring) -- a short data row (either table having run out)
# still gets padded out to this width so fixed-index slicing below never
# runs past the end of a list.
_COLUMN_COUNT = 11


class ContestEntry(BaseModel):
    rank: int
    entry_id: str
    entry_name: str
    points: float
    lineup_text: str


class ContestReferenceRow(BaseModel):
    player: str
    roster_position: str
    pct_drafted: float
    fpts: float


class ContestStandings(BaseModel):
    entries: list[ContestEntry]
    reference_rows: list[ContestReferenceRow]


def parse_lineup_text(lineup_text: str) -> list[tuple[str, str]]:
    """"DST Packers  FLEX TreVeyon Henderson QB Trevor Lawrence ..." ->
    [("DST", "Packers"), ("FLEX", "TreVeyon Henderson"), ("QB", "Trevor
    Lawrence"), ...] -- splits on the fixed slot tokens above rather than
    whitespace, so a multi-word player name (or the export's own stray
    double space before a slot token) never gets misread as a slot
    boundary. Each name is whatever falls between one slot token and the
    next, whitespace-trimmed."""
    matches = list(_SLOT_TOKEN_RE.finditer(lineup_text))
    pairs: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        slot = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(lineup_text)
        name = lineup_text[start:end].strip()
        if name:
            pairs.append((slot, name))
    return pairs


def _parse_float(value: str) -> float | None:
    value = value.strip().rstrip("%")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_contest_standings_csv(csv_text: str) -> ContestStandings:
    entries: list[ContestEntry] = []
    reference_rows: list[ContestReferenceRow] = []

    reader = csv.reader(io.StringIO(csv_text))
    next(reader, None)  # header row -- fixed column layout, read by position not name (see this module's docstring)

    for row in reader:
        if not row:
            continue
        row = row + [""] * (_COLUMN_COUNT - len(row))
        rank_text, entry_id, entry_name, _time_remaining, points_text, lineup_text = row[0:6]
        player, roster_position, pct_drafted_text, fpts_text = row[7:11]

        if rank_text.strip():
            entries.append(
                ContestEntry(
                    rank=int(rank_text),
                    entry_id=entry_id,
                    entry_name=entry_name,
                    points=_parse_float(points_text) or 0.0,
                    lineup_text=lineup_text,
                )
            )

        if player.strip():
            pct_drafted = _parse_float(pct_drafted_text)
            fpts = _parse_float(fpts_text)
            if pct_drafted is not None and fpts is not None:
                reference_rows.append(
                    ContestReferenceRow(
                        # DK's own export pads every DST row's Player cell
                        # with a trailing space (e.g. "Raiders ", "Packers
                        # "), unlike individual player names -- stripped
                        # here so every downstream exact-name lookup
                        # (salary file, tracker, ...) actually matches
                        # instead of silently missing every DST.
                        player=player.strip(),
                        roster_position=roster_position,
                        pct_drafted=pct_drafted,
                        fpts=fpts,
                    )
                )

    return ContestStandings(entries=entries, reference_rows=reference_rows)
