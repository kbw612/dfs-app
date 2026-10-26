"""
Loads one week of a past season's DraftKings main-slate GPP data into a
single normalized structure -- the training/validation input for the Lineup
Analyzer's factor weights (see the Lineup Analyzer plan: fit factor weights on
2025's real top finishers vs. a synthetic field, then test on 2026).

Four source files per week, all read from one folder (the person keeps these
outside the app's data folder, e.g. fantasy-data/NFL/2025/DK):

- DK-main-slate-contest-standings-week{N}.csv -- the top ~220-430 lineups of
  a 317,000-entry main-slate contest (about the top 0.1%), with points and
  a lineup string. Its right-hand player table is the SOURCE OF OWNERSHIP
  AND FPTS: one row per player with the main contest's own total %Drafted
  (summed over RB/WR/TE and FLEX slots) and actual FPTS. It is complete --
  the rows cover every drafted player, down to 0.00% ones, and the
  percentages add up to 900% (nine roster spots at 100% each) -- so a slate
  player missing from it is simply undrafted and gets 0.0.
- DKSalaries-week{N}.csv -- the all-games salary file (DK native format) for
  true position, team, salary and the DK player ID the export step needs. DST
  names carry a trailing space in some weeks ("Ravens "), so every name is
  stripped.
- DK-Players.csv -- one row per player per week for the whole season. Its
  %Drafted column comes from the ALL-GAMES contest, which is wrong for a
  main-slate field, so it is NOT used for ownership. It is only a fallback
  for a player's FPTS when he is absent from the standings table. "Main slate"
  is defined by the teams that appear in the top lineups.
- ownership-projections-week{N}.csv -- PRE-game projected ownership for about
  110-170 players (not every week has one). This, not the actual %Drafted, is
  what the analyzer will have on a live slate, so training uses it where it
  exists and marks the week otherwise.

Names join by exact string after stripping, plus an optional alias map
for spelling differences between sources.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from backend.services.contest_results.contest_standings_parser import (
    parse_contest_standings_csv,
    parse_lineup_text,
)

# Projection-file spellings that differ from the salary/contest spelling
# ({projection spelling: salary spelling}). Empty for 2025 -- every projected
# name that exists in the salary file already matches exactly (e.g. "James
# Cook III" is spelled that way in all sources).
DEFAULT_NAME_ALIASES: dict[str, str] = {}

# Fixed 9-slot Classic roster (see contest_standings_parser.py).
LINEUP_SIZE = 9


@dataclass
class HistoricalPlayer:
    name: str
    position: str
    team: str
    # The team he plays this week (from the salary file's "AWAY@HOME" game
    # info), "" when that info is missing.
    opponent: str
    salary: int
    dk_id: str | None
    # The main contest's actual total %Drafted (0.0 for a slate player absent
    # from the standings' player table, i.e. undrafted).
    actual_pct: float
    # Pre-game projected ownership (None when no projection exists for him).
    projected_pct: float | None
    fpts: float | None


@dataclass
class HistoricalLineup:
    rank: int
    points: float
    # (slot label from the lineup text, player) in file order; slot is
    # DST/FLEX/QB/RB/TE/WR, and FLEX players keep their real position.
    players: list[tuple[str, HistoricalPlayer]]


@dataclass
class HistoricalWeek:
    week: int
    # Teams that appear in the top lineups -- the main slate.
    main_slate_teams: set[str]
    # Every salaried player on a main-slate team, keyed by stripped name.
    pool: dict[str, HistoricalPlayer]
    lineups: list[HistoricalLineup]
    has_projections: bool
    # Human-readable problems found while loading (unmatched names, ...).
    issues: list[str] = field(default_factory=list)


def _pct(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().rstrip("%")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(value: str | None) -> int:
    text = (value or "").replace("$", "").replace(",", "").strip()
    return int(float(text)) if text else 0


def _opponent(game_info: str | None, team: str) -> str:
    """"KC@LV 09/14/2025 04:25PM ET" + team "KC" -> "LV"."""
    matchup = (game_info or "").split(" ")[0]
    if "@" not in matchup:
        return ""
    away, home = matchup.split("@", 1)
    return home if team == away else away if team == home else ""


def _read_salaries(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text.lstrip("﻿"))))


def parse_projections(csv_text: str, aliases: dict[str, str]) -> dict[str, float]:
    """{stripped player name: projected ownership %} -- tolerant of the
    optional unnamed index column some exports start with."""
    projected: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(csv_text.lstrip("﻿"))):
        name = (row.get("Player") or "").strip()
        pct = _pct(row.get("% ownership"))
        if name and pct is not None:
            projected[aliases.get(name, name)] = pct
    return projected


def load_week(
    folder: Path, week: int, aliases: dict[str, str] | None = None
) -> HistoricalWeek:
    """One week's HistoricalWeek. Raises FileNotFoundError if the standings or
    salary file is missing; a missing projections file just means
    has_projections=False."""
    aliases = DEFAULT_NAME_ALIASES if aliases is None else aliases
    issues: list[str] = []

    standings = parse_contest_standings_csv(
        (folder / f"DK-main-slate-contest-standings-week{week}.csv").read_text(encoding="utf-8-sig")
    )
    salary_rows = _read_salaries((folder / f"DKSalaries-week{week}.csv").read_text(encoding="utf-8-sig"))

    # Main-contest ownership and FPTS from the standings' own player table.
    # One row per player already, but summed anyway in case a file lists a
    # flex-eligible player once per slot.
    contest_pct: dict[str, float] = {}
    contest_fpts: dict[str, float] = {}
    for ref in standings.reference_rows:
        contest_pct[ref.player] = contest_pct.get(ref.player, 0.0) + ref.pct_drafted
        contest_fpts[ref.player] = ref.fpts

    # FPTS fallback for players absent from that table (undrafted ones).
    fallback_fpts: dict[str, float] = {}
    players_file = folder / "DK-Players.csv"
    if players_file.exists():
        for row in csv.DictReader(io.StringIO(players_file.read_text(encoding="utf-8-sig"))):
            if row.get("Week", "").strip() == str(week):
                value = _pct(row.get("FPTS"))
                if value is not None:
                    fallback_fpts[row["Name"].strip()] = value

    projections_file = folder / f"ownership-projections-week{week}.csv"
    projected = (
        parse_projections(projections_file.read_text(encoding="utf-8-sig"), aliases)
        if projections_file.exists()
        else {}
    )

    everyone: dict[str, HistoricalPlayer] = {}
    for row in salary_rows:
        name = (row.get("Name") or "").strip()
        if not name:
            continue
        everyone[name] = HistoricalPlayer(
            name=name,
            position=(row.get("Position") or "").strip(),
            team=(row.get("TeamAbbrev") or "").strip(),
            opponent=_opponent(row.get("Game Info"), (row.get("TeamAbbrev") or "").strip()),
            salary=_int(row.get("Salary")),
            dk_id=(row.get("ID") or "").strip() or None,
            actual_pct=contest_pct.get(name, 0.0),
            projected_pct=projected.get(name),
            fpts=contest_fpts.get(name, fallback_fpts.get(name)),
        )

    lineups: list[HistoricalLineup] = []
    slate_teams: set[str] = set()
    unresolved: dict[str, int] = {}
    for entry in standings.entries:
        pairs = parse_lineup_text(entry.lineup_text)
        if len(pairs) != LINEUP_SIZE:
            issues.append(f"rank {entry.rank}: {len(pairs)} players parsed, expected {LINEUP_SIZE}")
            continue
        resolved: list[tuple[str, HistoricalPlayer]] = []
        for slot, name in pairs:
            player = everyone.get(name)
            if player is None:
                unresolved[name] = unresolved.get(name, 0) + 1
                break
            resolved.append((slot, player))
        else:
            slate_teams.update(p.team for _, p in resolved)
            lineups.append(HistoricalLineup(rank=entry.rank, points=entry.points, players=resolved))
            continue
    for name, count in sorted(unresolved.items(), key=lambda kv: -kv[1]):
        issues.append(f"lineup player not in salary file: {name} ({count} lineups skipped)")

    pool = {name: p for name, p in everyone.items() if p.team in slate_teams}

    unmatched_projections = [n for n in projected if n not in everyone]
    if projected and unmatched_projections:
        issues.append(f"projection names not in salary file: {', '.join(sorted(unmatched_projections)[:8])}")
    if not projected:
        issues.append("no ownership projections for this week")

    return HistoricalWeek(
        week=week,
        main_slate_teams=slate_teams,
        pool=pool,
        lineups=lineups,
        has_projections=bool(projected),
        issues=issues,
    )
