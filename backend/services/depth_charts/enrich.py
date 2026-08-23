"""
Steps 2-3 of the pipeline (Section 2 of the design doc): enrich_team_abbrev()
and enrich_defensive_formation(). Both run in-memory, before the snapshot is
ever saved -- per the design doc, this is what keeps saved snapshots fully
immutable (no separate pass ever edits an already-saved file).

Partial failures don't abort the run: a team that can't be matched gets
`team_abbrev: null` and an error Message; the rest of the run continues.
"""

from __future__ import annotations

import csv
from pathlib import Path

from backend.schemas.depth_charts.snapshot import Message, Snapshot


def load_team_abbrev_map(csv_path: Path) -> dict[str, str]:
    """Reads config/team-info.csv (Team, Full Name, ...) into
    {full_name: abbrev}. Real content pulled from your GitHub repo
    (kbw612/Fantasy) at scaffold time -- see config/team-info.csv.
    """
    mapping: dict[str, str] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            full_name = row.get("Full Name", "").strip()
            abbrev = row.get("Team", "").strip()
            if full_name and abbrev:
                mapping[full_name] = abbrev
    return mapping


def enrich_team_abbrev(snapshot: Snapshot, team_info_csv_path: Path) -> Snapshot:
    abbrev_by_name = load_team_abbrev_map(team_info_csv_path)

    matched = 0
    for team in snapshot.teams:
        abbrev = abbrev_by_name.get(team.team_name)
        if abbrev:
            team.team_abbrev = abbrev
            matched += 1
        else:
            team.team_abbrev = None
            snapshot.messages.append(
                Message(
                    level="error",
                    step="enrich_team_abbrev",
                    message=(
                        f"No abbreviation match found for team name '{team.team_name}' "
                        "-- check team-info.csv for a naming mismatch"
                    ),
                )
            )

    snapshot.messages.append(
        Message(
            level="info",
            step="enrich_team_abbrev",
            message=f"Matched team_abbrev for {matched} of {len(snapshot.teams)} teams",
        )
    )
    return snapshot


def compute_defensive_formation(positions: dict[str, list]) -> str | None:
    """4-3 if MLB is populated, 3-4 if NT is instead, null if neither
    (hybrid front, or a scraping gap)."""
    if len(positions.get("MLB", [])) > 0:
        return "4-3"
    elif len(positions.get("NT", [])) > 0:
        return "3-4"
    return None


def enrich_defensive_formation(snapshot: Snapshot) -> Snapshot:
    resolved = 0
    for team in snapshot.teams:
        formation = compute_defensive_formation(
            {pos: players for pos, players in team.positions.items()}
        )
        team.defensive_formation = formation
        if formation is None:
            snapshot.messages.append(
                Message(
                    level="warning",
                    step="enrich_defensive_formation",
                    message=f"Both MLB and NT empty for '{team.team_name}' -- defaulted to null",
                )
            )
        else:
            resolved += 1

    snapshot.messages.append(
        Message(
            level="info",
            step="enrich_defensive_formation",
            message=f"Resolved defensive_formation for {resolved} of {len(snapshot.teams)} teams",
        )
    )
    return snapshot
