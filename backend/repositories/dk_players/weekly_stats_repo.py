"""
Persists the 5 FantasyData stat exports (QB/RB/WR/TE/DST -- see
backend/services/dk_players/weekly_stats_loader.py for the column shape
each one has) that feed DK Players' calculate_week_points(). One file per
(season, position) -- FantasyData_QBs.csv, FantasyData_RBs.csv,
FantasyData_WRs.csv, FantasyData_TEs.csv, FantasyData_DSTs.csv -- that
grows across the season as each week's stats are saved into it, unlike
every other per-week snapshot in this app which is one file per week.
These are league-wide stats, not tied to a DK platform/contest, so
there's no platform dimension here either.

DST's file has the same shape as the other four (NAME/TEAM/WK/RK columns
and all) even though its NAME is a team nickname rather than a player --
see weekly_stats_scraper.py's DST-specific parsing for why. RK is still a
real per-week rank (1..N, sorted by that week's FPTS) synthesized by the
scraper itself since the source page has no rank column of its own, so
the (WK, RK) sort key below works unchanged for DST too.

Each scrape (see backend/services/dk_players/weekly_stats_scraper.py)
hands in exactly one week's rows. merge_week_into_season_csv folds those
into the season file: any rows already saved for that same week
(identified by the file's own WK column) are dropped and replaced by the
new ones, every other week's rows are left untouched. Rows are kept
sorted by (WK, RK) so the file reads as a clean week-by-week log
regardless of what order saves happened to occur in.

write_usage_share_columns is a separate, later write to the same file --
it doesn't touch any of the raw FantasyData columns merge_week_into_season_csv
manages, only appends/updates this app's own TGT_SHARE/TOUCH_SHARE/OPP_SHARE
trailing columns (see backend/services/shared/usage_shares.py), once "Calc
Week Points" has computed them for a given week.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Literal

Position = Literal["QB", "RB", "WR", "TE", "DST"]

_FILENAME_BY_POSITION: dict[Position, str] = {
    "QB": "FantasyData_QBs.csv",
    "RB": "FantasyData_RBs.csv",
    "WR": "FantasyData_WRs.csv",
    "TE": "FantasyData_TEs.csv",
    "DST": "FantasyData_DSTs.csv",
}


def _path(nfl_data_dir: Path, season: int, position: Position) -> Path:
    return nfl_data_dir / str(season) / _FILENAME_BY_POSITION[position]


def weekly_stats_csv_path(nfl_data_dir: Path, season: int, position: Position) -> Path:
    return _path(nfl_data_dir, season, position)


def load_weekly_stats_csv(nfl_data_dir: Path, season: int, position: Position) -> str | None:
    """The whole season-long file (every week saved so far), or None if
    nothing's ever been saved for this (season, position). Callers that
    only care about one week (e.g. weekly_stats_loader.parse_weekly_stats_csv)
    filter the returned text by its own WK column."""
    file_path = _path(nfl_data_dir, season, position)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")


def _row_week(row: dict[str, str]) -> int | None:
    try:
        return int(row["WK"])
    except (KeyError, ValueError, TypeError):
        return None


def _row_rank(row: dict[str, str]) -> int:
    try:
        return int(row.get("RK") or 0)
    except (ValueError, TypeError):
        return 0


def week_has_data(nfl_data_dir: Path, season: int, position: Position, week: int) -> bool:
    """Whether `week` already has rows saved in this position's season
    file -- lets a caller warn before a re-scrape/re-upload overwrites
    them, since the file itself always exists after the first week is
    ever saved (so file-existence alone can't answer that question)."""
    csv_text = load_weekly_stats_csv(nfl_data_dir, season, position)
    if csv_text is None:
        return False
    return any(_row_week(row) == week for row in csv.DictReader(io.StringIO(csv_text)))


def merge_week_into_season_csv(
    nfl_data_dir: Path, season: int, position: Position, week: int, week_csv_text: str
) -> Path:
    """Folds one week's freshly-uploaded/scraped CSV text into this
    position's season-long file. Existing rows for `week` are dropped and
    replaced by `week_csv_text`'s own rows; every other week's rows are
    kept as-is. The merged file's header is the new week's header, plus
    any extra columns an older season file happened to have that the new
    header doesn't (defensive against FantasyData's column set drifting
    over time -- in practice the two always match)."""
    new_reader = csv.reader(io.StringIO(week_csv_text))
    new_header = next(new_reader, [])
    new_rows = list(csv.DictReader(io.StringIO(week_csv_text)))

    existing_text = load_weekly_stats_csv(nfl_data_dir, season, position)
    existing_header: list[str] = []
    existing_rows: list[dict[str, str]] = []
    if existing_text is not None:
        existing_header = next(csv.reader(io.StringIO(existing_text)), [])
        existing_rows = [row for row in csv.DictReader(io.StringIO(existing_text)) if _row_week(row) != week]

    merged_header = list(new_header)
    for column in existing_header:
        if column not in merged_header:
            merged_header.append(column)

    merged_rows = existing_rows + new_rows
    merged_rows.sort(key=lambda row: ((_row_week(row) if _row_week(row) is not None else 0), _row_rank(row)))

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=merged_header, restval="")
    writer.writeheader()
    writer.writerows(merged_rows)

    file_path = _path(nfl_data_dir, season, position)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(buffer.getvalue(), encoding="utf-8")
    return file_path


def write_usage_share_columns(
    nfl_data_dir: Path,
    season: int,
    position: Position,
    week: int,
    shares_by_player: dict[str, tuple[float | None, float | None, float | None]],
) -> None:
    """Writes `week`'s freshly-computed (target_share_pct, touch_share_pct,
    opp_share_pct) values (see backend/services/shared/usage_shares.py's
    compute_usage_share_updates) onto this position's own season file, as
    three trailing columns ("TGT_SHARE", "TOUCH_SHARE", "OPP_SHARE") --
    appended to the header the first time any of them is ever written,
    same backward-compatible-column convention as dk_players_csv.py's own
    trailing columns. Only rows matching `week` are touched; every other
    week's already-written values (if any) are left exactly as they were.
    A no-op if this position has no season file at all yet (nothing to
    write into).

    A missing entry in `shares_by_player` for a given row (shouldn't
    happen -- the caller builds it from this same file's own week-`week`
    rows -- but defensive against a name that doesn't round-trip cleanly)
    writes blank cells, same as explicit None share values."""
    existing_text = load_weekly_stats_csv(nfl_data_dir, season, position)
    if existing_text is None:
        return
    header = next(csv.reader(io.StringIO(existing_text)), [])
    rows = list(csv.DictReader(io.StringIO(existing_text)))

    for column in ("TGT_SHARE", "TOUCH_SHARE", "OPP_SHARE"):
        if column not in header:
            header.append(column)

    for row in rows:
        if _row_week(row) != week:
            continue
        name = row.get("NAME", "").strip()
        target_share_pct, touch_share_pct, opp_share_pct = shares_by_player.get(name, (None, None, None))
        row["TGT_SHARE"] = "" if target_share_pct is None else str(target_share_pct)
        row["TOUCH_SHARE"] = "" if touch_share_pct is None else str(touch_share_pct)
        row["OPP_SHARE"] = "" if opp_share_pct is None else str(opp_share_pct)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, restval="")
    writer.writeheader()
    writer.writerows(rows)

    file_path = _path(nfl_data_dir, season, position)
    file_path.write_text(buffer.getvalue(), encoding="utf-8")
