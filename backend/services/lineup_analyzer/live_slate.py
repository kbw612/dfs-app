"""
Builds a HistoricalWeek-shaped pool for a LIVE slate from the app's uploaded
DK salary file and ownership projections, so the synthetic field and the
feature code written for 2025 history can be reused unchanged.

Ownership = projected % where the projections file lists the player, else the
lowest projected value (the file lists only the most relevant players -- same
rule as features.scoring_ownership). Points are unknown (0).
"""

from __future__ import annotations

import csv
import io

from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct
from backend.services.lineup_analyzer.history_loader import HistoricalPlayer, HistoricalWeek
from backend.services.ownership.parsing import UNDER_ONE_ANALYZER_PCT, is_under_one_placeholder


class SlateError(ValueError):
    """Missing salary file / projections for the requested slate."""


def build_live_week(
    salary_csv_text: str | None, ownership_players, season: int, week: int
) -> tuple[HistoricalWeek, dict[str, str]]:
    """Returns (week, id_to_name). Raises SlateError when an input is missing."""
    if salary_csv_text is None:
        raise SlateError("No DK salary file uploaded for this week/contest -- upload it in Settings first.")
    if not ownership_players:
        raise SlateError("No ownership projections uploaded for this week -- upload them in Settings first.")

    snapshot, _messages = parse_dk_salary_csv(salary_csv_text, season, week)
    players = enrich_with_ownership_pct(snapshot.players, ownership_players)

    id_to_name: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(salary_csv_text)):
        name = (row.get("Name") or "").strip()
        pid = (row.get("ID") or "").strip()
        if name and pid:
            id_to_name[pid] = name
            name_to_id[name] = pid

    # The "<1%" placeholder (0.001) counts as UNDER_ONE_ANALYZER_PCT in the field.
    players = [
        p.model_copy(update={"ownership_pct": UNDER_ONE_ANALYZER_PCT}) if is_under_one_placeholder(p.ownership_pct) else p
        for p in players
    ]
    projected = [p.ownership_pct for p in players if p.ownership_pct is not None]
    if not projected:
        raise SlateError("Ownership projections did not match any player in the salary file.")
    default = min(projected)

    pool: dict[str, HistoricalPlayer] = {}
    for p in players:
        name = p.player.strip()
        pct = p.ownership_pct if p.ownership_pct is not None else default
        pool[name] = HistoricalPlayer(
            name=name,
            position=p.position,
            team=p.team,
            opponent=p.opponent or "",
            salary=p.salary,
            dk_id=name_to_id.get(name),
            actual_pct=pct,
            projected_pct=p.ownership_pct,
            fpts=0.0,
        )
    return HistoricalWeek(week, {p.team for p in pool.values()}, pool, [], True, []), id_to_name
