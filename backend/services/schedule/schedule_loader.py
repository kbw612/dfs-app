"""
Parses the full-season Team/Week/Opponent/GameLocation schedule CSV
(backend/repositories/schedule/schedule_repo.py -- one file per season,
covering every week at once, uploaded via Settings) into ScheduleRow
records, and provides the two lookups the Game Logs tab needs: a given
team's opponent/home-away for one week (opponent_and_location), and every
matchup for one week (games_for_week, used to build the Game filter's
options -- see game_logs_engine.py's build_game_options).

Column names match the person's own schedule export exactly: Team, Week,
Opponent, GameLocation (values "Home" or "Away", or "BYE" as Opponent for
a bye week -- see opponent_and_location's own docstring for how that's
normalized).
"""

from __future__ import annotations

import csv
import io
from typing import NamedTuple


class ScheduleRow(NamedTuple):
    team: str
    week: int
    opponent: str
    game_location: str


# A schedule export's own team codes don't always agree with DK's own
# abbreviations (the DK Players tracker's TeamAbbrev, which every other
# lookup in this app -- and games_for_week/opponent_and_location's own
# callers -- treats as canonical). Jacksonville is the one confirmed
# mismatch so far (schedule exports commonly use "JAC", DK's salary/
# tracker files always say "JAX" -- same "JAX"/"jags" alias Vegas Lines'
# own team-name table already normalizes to, see
# backend/services/vegas_lines/scraper.py). Without this, a row's team
# code silently fails to match any DK Players tracker row for that team,
# so that team's players never appear in Game Logs when its game is
# selected (see _normalize_team's callers below) even though the team
# itself shows up fine in the schedule/games list. Add more entries here
# if another schedule source turns up a different non-DK spelling.
_TEAM_ABBREV_ALIASES = {"JAC": "JAX"}


def _normalize_team(code: str) -> str:
    return _TEAM_ABBREV_ALIASES.get(code, code)


def parse_schedule_csv(csv_text: str) -> list[ScheduleRow]:
    """Skips any row missing a usable Week or Team -- defensive against a
    stray blank line, same spirit as every other CSV parser in this app.
    Team and Opponent are both normalized to DK's own abbreviations (see
    _TEAM_ABBREV_ALIASES) -- Opponent's "BYE" sentinel is left untouched,
    same as opponent_and_location's own BYE handling below."""
    rows: list[ScheduleRow] = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        team = (row.get("Team") or "").strip()
        if not team:
            continue
        try:
            week = int(row["Week"])
        except (KeyError, ValueError):
            continue
        team = _normalize_team(team)
        opponent = (row.get("Opponent") or "").strip()
        if opponent != "BYE":
            opponent = _normalize_team(opponent)
        game_location = (row.get("GameLocation") or "").strip()
        rows.append(ScheduleRow(team=team, week=week, opponent=opponent, game_location=game_location))
    return rows


def opponent_and_location(rows: list[ScheduleRow], team: str, week: int) -> tuple[str, str] | None:
    """(opponent, game_location) for this team/week, or None if the
    schedule has no row for it (schedule not uploaded yet, or a team code
    that doesn't match) -- callers render "-" either way, same graceful-
    degradation convention as every other missing-side-channel-data case
    in this app. A bye week's own row (Opponent == "BYE") always comes
    back as exactly ("BYE", "BYE"), regardless of whatever the raw file's
    GameLocation column happened to say for that row -- "home"/"away" is
    meaningless for a week with no game."""
    for row in rows:
        if row.team == team and row.week == week:
            if row.opponent == "BYE":
                return ("BYE", "BYE")
            return (row.opponent, row.game_location)
    return None


def games_for_week(rows: list[ScheduleRow], week: int) -> list[frozenset[str]]:
    """Every distinct matchup for `week` as a 2-team set -- both teams'
    own schedule rows collapse to the same matchup, and a bye week
    (Opponent == "BYE") contributes nothing (there's no game to pick).
    Order is whatever dict insertion order the rows came in; callers that
    want a stable display order (e.g. alphabetical) sort it themselves."""
    seen: dict[frozenset[str], None] = {}
    for row in rows:
        if row.week != week or row.opponent == "BYE" or not row.opponent:
            continue
        key = frozenset({row.team, row.opponent})
        seen.setdefault(key, None)
    return list(seen.keys())
