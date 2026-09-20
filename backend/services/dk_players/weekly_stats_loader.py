"""
Parses FantasyData stat exports (QB, RB, WR, or TE -- see
backend/repositories/dk_players/weekly_stats_repo.py) two ways:

1. parse_weekly_stats_csv/merge_td_points -- one week's {player_name:
   td_points} map, feeding DK Players' calculate_week_points().

2. load_weekly_stat_lines -- every week's raw usage stats (team/targets/
   receptions/receiving_yards/rush_att/rush_yards, plus QB's own passing
   line -- pass_cmp/pass_att/pass_cmp_pct/pass_yds/pass_avg/pass_td/
   pass_int/pass_sck/pass_rtg) at once, keyed by (player, week), feeding
   the Game Logs tab's Touch/TGTS/REC/REC_YDS/RUSH_ATT/RUSH_YDS/Pass
   columns -- unlike (1), Game Logs needs a whole season's history in one
   pass, not just the single most-recent week.

   TGTSHARE/TOUCHSHARE/OPPSHARE (target_share_pct/touch_share_pct/
   opp_share_pct) are also read here, from this same file's own
   TGT_SHARE/TOUCH_SHARE/OPP_SHARE columns -- three extra trailing
   columns this app adds on top of FantasyData's own layout (see
   backend/services/shared/usage_shares.py and
   backend/repositories/dk_players/weekly_stats_repo.py's
   write_usage_share_columns), written once by the "Calc Week Points"
   action, not computed live here. A file that predates one of those
   columns simply has no matching header at all, so that key is omitted
   from the stat line entirely (same "not applicable yet" convention as
   every other optional column below); once a column exists, a blank
   cell (not yet computed for that row, or QB's own always-blank
   TGT_SHARE) parses to None rather than 0.

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


def _parse_float(value: str | None) -> float:
    """Same blank-cell-defaults-to-0 spirit as _parse_int, but for QB's
    own decimal passing columns (CMP%, AVG, RATING) -- int() would
    truncate a real value like a 124.1 passer rating."""
    if value is None or value.strip() == "":
        return 0.0
    return float(value)


def _parse_optional_float(value: str | None) -> float | None:
    """None (not 0) for a blank TGT_SHARE/TOUCH_SHARE/OPP_SHARE cell --
    unlike every other numeric column in this file, a blank share cell
    means "not yet computed" or "not applicable" (QB's own TGT_SHARE), not
    a real 0 -- see this module's own docstring."""
    if value is None or value.strip() == "":
        return None
    return float(value)


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

# QB's own passing line -- only the QB file carries these columns at all
# (RB/WR/TE have none of them), so the same "missing column -> key simply
# omitted" convention as _USAGE_STAT_COLUMNS above makes every non-QB
# player's stat line naturally have none of these keys, no per-position
# branching needed. Split into int vs. float groups since CMP%/AVG/RATING
# are real decimals (_parse_int would truncate a 124.1 passer rating).
_PASSING_STAT_INT_COLUMNS = {
    "pass_cmp": "PASSING_CMP",
    "pass_att": "PASSING_ATT",
    "pass_yds": "PASSING_YDS",
    "pass_td": "PASSING_TD",
    "pass_int": "INT",
    "pass_sck": "SCK",
}
_PASSING_STAT_FLOAT_COLUMNS = {
    "pass_cmp_pct": "PASSING_CMP%",
    "pass_avg": "PASSING_AVG",
    "pass_rtg": "RATING",
}


def load_weekly_stat_lines(csv_text: str) -> dict[tuple[str, int], dict[str, int | float | str]]:
    """Every row's raw usage stats (plus QB's own passing line) and its
    own team, keyed by (player name, week) -- reads every week already
    saved in the file at once (unlike parse_weekly_stats_csv, which
    filters to exactly one week), since Game Logs needs a whole season's
    worth of usage numbers in a single pass. A stat column this position's
    file doesn't have is left out of that row's dict entirely rather than
    defaulted to 0 -- callers use dict.get(key, 0) explicitly wherever a
    numeric default is wanted.

    "team" is always present (every FantasyData file has a TEAM column,
    unlike the position-specific usage columns) -- it's what lets
    game_logs_engine.py group every player's own line by team to compute
    that team's weekly target/touch totals for Target Share %/Touch
    Share %, without a separate parse pass just for that."""
    lines: dict[tuple[str, int], dict[str, int | float | str]] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        try:
            week = int(row["WK"])
        except (KeyError, ValueError):
            continue
        name = row.get("NAME", "").strip()
        if not name:
            continue
        stat_line: dict[str, int | float | str] = {
            key: _parse_int(row[column]) for key, column in _USAGE_STAT_COLUMNS.items() if column in row
        }
        stat_line.update(
            {key: _parse_int(row[column]) for key, column in _PASSING_STAT_INT_COLUMNS.items() if column in row}
        )
        stat_line.update(
            {key: _parse_float(row[column]) for key, column in _PASSING_STAT_FLOAT_COLUMNS.items() if column in row}
        )
        # See this module's own docstring -- these three are only present
        # once "Calc Week Points" has written them via
        # write_usage_share_columns; an older/not-yet-computed file simply
        # has no "TGT_SHARE"/"TOUCH_SHARE"/"OPP_SHARE" header at all.
        if "TGT_SHARE" in row:
            stat_line["target_share_pct"] = _parse_optional_float(row["TGT_SHARE"])
        if "TOUCH_SHARE" in row:
            stat_line["touch_share_pct"] = _parse_optional_float(row["TOUCH_SHARE"])
        if "OPP_SHARE" in row:
            stat_line["opp_share_pct"] = _parse_optional_float(row["OPP_SHARE"])
        stat_line["team"] = row.get("TEAM", "").strip()
        lines[(name, week)] = stat_line
    return lines
