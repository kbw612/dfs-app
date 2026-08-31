"""
Loads DraftKings' own native salary export ("DKSalaries.csv") into the
shared DkSalarySnapshot -- a different column shape than the
ownership-projections CSV backend/services/ownership/csv_loader.py reads
(Player, Position, Team, Opponent, Salary, % ownership). This one has
Position, "Name + ID", Name, ID, Roster Position, Salary, Game Info,
TeamAbbrev, AvgPointsPerGame, Status -- no ownership column at all (DK's
own export never has ownership %), and opponent/home-away have to be
parsed out of the combined "Game Info" column instead of being separate
columns (see dk_salary_parsing.parse_game_info).

This is the one shared upload behind Salary Blocks and Player Pool (see
backend/api/dk_salary/import_csv.py) -- deliberately its own loader rather
than extending csv_loader.py, since neither of those tabs should depend on
the Ownership tab having loaded anything for the week; uploading this file
is enough on its own. Produces the same OwnershipPlayer row shape
csv_loader.py does (ownership_pct always None here) so callers don't care
which loader produced their input -- see backend/services/dk_salary/
ownership_enrich.py for how ownership_pct gets opportunistically filled in
afterward when the Ownership tab happens to have a snapshot for the same
week.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from backend.schemas.depth_charts.snapshot import Message
from backend.schemas.dk_salary.salary_snapshot import DkSalarySnapshot
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.dk_salary.dk_salary_parsing import parse_game_info
from backend.services.ownership.parsing import normalize_team_abbrev, parse_salary


def parse_dk_salary_csv(csv_text: str, season: int, week: int) -> tuple[DkSalarySnapshot, list[Message]]:
    players: list[OwnershipPlayer] = []
    messages: list[Message] = []

    for row in csv.DictReader(io.StringIO(csv_text)):
        name = row.get("Name", "?")
        try:
            team = normalize_team_abbrev(row["TeamAbbrev"])
            opponent, is_home = parse_game_info(row["Game Info"], team)
            salary = parse_salary(row["Salary"])
            position = row["Position"].strip()
        except (KeyError, ValueError) as exc:
            messages.append(
                Message(
                    level="warning",
                    step="dk-salary-import-csv",
                    message=f"Couldn't parse row for {name!r} -- row skipped ({exc})",
                )
            )
            continue

        players.append(
            OwnershipPlayer(
                player=name,
                position=position,
                team=team,
                opponent=opponent,
                is_home=is_home,
                salary=salary,
                ownership_pct=None,
            )
        )

    if not players:
        messages.append(Message(level="error", step="dk-salary-import-csv", message="No players parsed from CSV"))

    snapshot = DkSalarySnapshot(
        scraped_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        source_url="upload://dk-salaries.csv",
        season=season,
        week=week,
        players=players,
    )
    return snapshot, messages
