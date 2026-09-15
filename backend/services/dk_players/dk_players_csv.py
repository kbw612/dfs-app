"""
Round-trip CSV (de)serialization for the DK Players tracker's own storage
format -- see backend/repositories/dk_players/dk_players_repo.py for why
this is a single growing file rather than a per-week snapshot. Column
names mirror the person's own original DK-Players.csv (Name, Position,
Roster Position, TeamAbbrev, Week, Salary, %Drafted, FPTS, Non_TD_FPTS,
TD_FPTS) for familiarity, though %Drafted is stored as a plain number
here (e.g. "24.21") rather than that file's "24.21%" string -- this CSV is
purely this app's own internal storage (no download/export requirement),
so there's no need to match the legacy formatting exactly, just the
column names and order.
"""

from __future__ import annotations

import csv
import io

from backend.schemas.dk_players.dk_players import DkPlayerRow

HEADER = [
    "Name",
    "Position",
    "Roster Position",
    "TeamAbbrev",
    "Week",
    "Salary",
    "%Drafted",
    "FPTS",
    "Non_TD_FPTS",
    "TD_FPTS",
]


def _parse_pct_drafted(value: str) -> float:
    """This app's own storage always writes a bare number (see this
    module's docstring), but someone hand-editing/replacing this file with
    their own legacy export (e.g. a prior season's DK-Players.csv, which
    used a literal "24.21%" string) is a real, observed failure mode --
    float("24.21%") raises ValueError, which previously surfaced as an
    unhandled 500 on every endpoint that reads the tracker. Stripping a
    trailing "%" if present keeps both formats working rather than
    requiring the file to be manually cleaned first."""
    return float(value.strip().rstrip("%"))


def parse_dk_players_csv(csv_text: str) -> list[DkPlayerRow]:
    """Empty string (a season/platform with no tracker file yet) parses to
    an empty list rather than requiring callers to special-case None vs.
    "" themselves."""
    if not csv_text.strip():
        return []
    rows: list[DkPlayerRow] = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        rows.append(
            DkPlayerRow(
                name=row["Name"],
                position=row["Position"],
                roster_position=row["Roster Position"],
                team=row["TeamAbbrev"],
                week=int(row["Week"]),
                salary=int(row["Salary"]),
                pct_drafted=_parse_pct_drafted(row["%Drafted"]),
                fpts=float(row["FPTS"]),
                non_td_fpts=float(row["Non_TD_FPTS"]),
                td_fpts=float(row["TD_FPTS"]),
            )
        )
    return rows


def serialize_dk_players_csv(rows: list[DkPlayerRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow(
            [
                row.name,
                row.position,
                row.roster_position,
                row.team,
                row.week,
                row.salary,
                row.pct_drafted,
                row.fpts,
                row.non_td_fpts,
                row.td_fpts,
            ]
        )
    return buffer.getvalue()
