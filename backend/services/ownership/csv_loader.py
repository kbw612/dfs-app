"""
Temporary stand-in for scraper.py's live login+scrape: builds the exact
same OwnershipSnapshot shape by reading DK ownership CSVs off local disk
instead of authenticating against oneweekseason.com. Everything
downstream (snapshot_repo, engine.py, the API layer) doesn't know or care
which of the two produced the snapshot -- this is deliberately a drop-in
alternative to scraper.scrape(), not a separate code path the rest of the
app has to special-case.

Expects the same two-CSV shape the original high_owned_players.py
notebook produced: an offense file (every non-DST position) and an
optional DST file, both with columns Player/Position/Team/Opponent/
Salary/% ownership -- an extra leading empty-header index column (from
pandas' `to_csv(index=True)`) is harmless and ignored. Reuses
parsing.py's salary/ownership/team/opponent parsing so a row parses
identically whether it came from this CSV path or the live HTML table.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from backend.schemas.depth_charts.snapshot import Message
from backend.schemas.ownership.ownership import OwnershipPlayer, OwnershipSnapshot
from backend.services.ownership.parsing import normalize_team_abbrev, parse_opponent, parse_ownership_pct, parse_salary


def _parse_csv_rows(path: Path, label: str) -> tuple[list[OwnershipPlayer], list[Message]]:
    players: list[OwnershipPlayer] = []
    messages: list[Message] = []

    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            player_name = row.get("Player", "?")
            try:
                team = normalize_team_abbrev(row["Team"])
                opponent, is_home = parse_opponent(row["Opponent"])
                salary = parse_salary(row["Salary"])
                ownership_pct = parse_ownership_pct(row["% ownership"])
            except (KeyError, ValueError):
                messages.append(
                    Message(
                        level="warning",
                        step="import-csv",
                        message=f"Couldn't parse {label} row for {player_name!r} -- row skipped",
                    )
                )
                continue

            players.append(
                OwnershipPlayer(
                    player=player_name,
                    position=row["Position"],
                    team=team,
                    opponent=opponent,
                    is_home=is_home,
                    salary=salary,
                    ownership_pct=ownership_pct,
                )
            )

    return players, messages


def load_ownership_csv(season: int, week: int, mock_dir: Path) -> tuple[OwnershipSnapshot, list[Message]]:
    """Loads "ownership-projections-week{week}.csv" (required) and
    "dst-ownership-projections-week{week}.csv" (optional -- DST is just
    another position here, but the original notebook always split it into
    its own file, so both are supported) from `mock_dir`."""
    offense_path = mock_dir / f"ownership-projections-week{week}.csv"
    dst_path = mock_dir / f"dst-ownership-projections-week{week}.csv"

    messages: list[Message] = []
    if not offense_path.exists():
        messages.append(
            Message(level="error", step="import-csv", message=f"Offense CSV not found: {offense_path}")
        )
        return OwnershipSnapshot(
            scraped_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            source_url=f"file://{offense_path}",
            season=season,
            week=week,
            players=[],
        ), messages

    players, offense_messages = _parse_csv_rows(offense_path, "offense")
    messages.extend(offense_messages)

    if dst_path.exists():
        dst_players, dst_messages = _parse_csv_rows(dst_path, "DST")
        players.extend(dst_players)
        messages.extend(dst_messages)
    else:
        messages.append(
            Message(level="warning", step="import-csv", message=f"DST CSV not found (skipped): {dst_path}")
        )

    if not players:
        messages.append(Message(level="warning", step="import-csv", message="No players parsed from CSV"))

    snapshot = OwnershipSnapshot(
        scraped_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        source_url=f"file://{offense_path}",
        season=season,
        week=week,
        players=players,
    )
    return snapshot, messages
