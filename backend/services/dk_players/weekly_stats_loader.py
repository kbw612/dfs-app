"""
Parses FantasyData stat exports (QB, RB, WR, or TE -- see
backend/repositories/dk_players/weekly_stats_repo.py) two ways:

1. parse_weekly_stats_csv/merge_td_points -- one week's {player_name:
   td_points} map, feeding DK Players' calculate_week_points().

2. load_weekly_stat_lines -- every week's raw usage stats (targets/
   receptions/receiving_yards/rush_att/rush_yards) at once, keyed by
   (player, week), feeding the Game Logs tab's Touch/TGTS/REC/REC_YDS/
   RUSH_ATT/RUSH_YDS columns (backend/services/game_logs/
   game_logs_engine.py) -- unlike (1), Game Logs needs a whole season's
   history in one pass, not just the single most-recent week.

Each position's export has a different column set, but every one that can
score a touchdown carries RUSHING_TD, and WR/RB/TE additionally carry
RECEIVING_TD while only QB carries PASSING_TD -- see this module's own
_TD_POINT_VALUES for the DK-scoring point value of each. A cell that's
missing/blank (e.g. RUSHING_YDS/AVG often blank when RUSHING_ATT is 0)
parses as 0 rather than raising, same defensive-parsing spirit as
dk_salary_loader.py.
"""

from __future__ import annotations

import csv
import io
from typing import Literal

Position = Literal["QB", "RB", "WR", "TE"]

# DK standard scoring's own points-per-touchdown -- passing TDs are worth
# 4, every other touchdown (rushing or receiving, regardless of position)
# is worth 6. Matches the person's own prior Colab script exactly.
_TD_POINT_VALUES = {"PASSING_TD": 4, "RUSHING_TD": 6, "RECEIVING_TD": 6}


def _parse_int(value: str | None) -> int:
    if value is None or value.strip() == "":
        return 0
    return int(float(value))


def parse_weekly_stats_csv(csv_text: str, week: int) -> dict[str, float]:
    """{player_name: td_points} for every row in this file whose own WK
    column matches `week` -- defensive against an accidentally-wrong file
    being uploaded for this week, even though in practice each upload is
    already scoped to one week. A player who appears with 0 touchdowns
    still gets an entry (0.0), which matters for calculate_week_points --
    an explicit 0 there beats a caller mistaking a matched-but-scoreless
    player for an unmatched one."""
    td_points: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        try:
            row_week = int(row["WK"])
        except (KeyError, ValueError):
            continue
        if row_week != week:
            continue
        name = row.get("NAME", "").strip()
        if not name:
            continue
        points = sum(_parse_int(row.get(column)) * value for column, value in _TD_POINT_VALUES.items() if column in row)
        td_points[name] = float(points)
    return td_points


def merge_td_points(stats_csvs: dict[Position, str], week: int) -> dict[str, float]:
    """Combines all 4 position files' own td_points maps into one --
    a player only ever appears in one position's file, so this is a
    plain union, not a sum-across-files merge (unlike the person's own
    Colab script, which did a clunkier outer-join across all 4 to the
    same effect)."""
    merged: dict[str, float] = {}
    for csv_text in stats_csvs.values():
        merged.update(parse_weekly_stats_csv(csv_text, week))
    return merged


# Which raw usage-stat column each position's file carries, mapped to the
# stat-line key Game Logs reads it back out by -- QB's file has no
# RECEIVING_* columns at all (see weekly_stats_scraper.py's own header
# maps), so a QB's stat line simply won't have "targets"/"receptions"/
# "receiving_yards" keys, letting callers tell "not applicable to this
# position" apart from "really was 0" (see load_weekly_stat_lines below).
_USAGE_STAT_COLUMNS = {
    "targets": "RECEIVING_TGTS",
    "receptions": "RECEIVING_REC",
    "receiving_yards": "RECEIVING_YDS",
    "rush_att": "RUSHING_ATT",
    "rush_yards": "RUSHING_YDS",
}


def load_weekly_stat_lines(csv_text: str) -> dict[tuple[str, int], dict[str, int]]:
    """Every row's raw usage stats, keyed by (player name, week) -- reads
    every week already saved in the file at once (unlike
    parse_weekly_stats_csv, which filters to exactly one week), since Game
    Logs needs a whole season's worth of usage numbers in a single pass.
    A stat column this position's file doesn't have is left out of that
    row's dict entirely rather than defaulted to 0 -- callers use
    dict.get(key, 0) explicitly wherever a numeric default is wanted."""
    lines: dict[tuple[str, int], dict[str, int]] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        try:
            week = int(row["WK"])
        except (KeyError, ValueError):
            continue
        name = row.get("NAME", "").strip()
        if not name:
            continue
        stat_line = {key: _parse_int(row[column]) for key, column in _USAGE_STAT_COLUMNS.items() if column in row}
        lines[(name, week)] = stat_line
    return lines
