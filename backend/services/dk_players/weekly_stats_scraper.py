"""
Scrapes FantasyData.com's public "Fantasy Football Leaders" page
(https://fantasydata.com/nfl/fantasy-football-leaders) for one week's
QB/RB/WR/TE game-log stats -- the same 4 files Settings' Weekly Stats
panel otherwise expects as a manual CSV upload (see
backend/repositories/dk_players/weekly_stats_repo.py). No login is
required: the leaders table is fully server-rendered and readable
anonymously (confirmed empirically -- a plain `requests.get()` with no
session/cookies returns the complete table). The page always shows a "See
all rows with Premium access" banner below the table, but that's a
generic, always-present upsell CTA, not an actual row cap -- a table with
only a handful of rows mid-week simply means only that many players have
accrued stats so far (e.g. 6 QBs after only 2 games had been played in
Week 1 2026), not that the rest are hidden.

URL shape: ?scope=game&sp={season}_REG&week_from={week}&week_to={week}
&position={qb|rb|wr|te}&scoring=fpts_ppr&pivot=0&order_by=fpts_ppr
&sort_dir=desc -- `week_from`/`week_to` both set to the same week limits
the table to that single week's game log (one row per player, matching
the manual-upload files' own one-row-per-player-per-week shape).

The stats table (`table.stats`) has a two-row <thead>: the first row is
just group labels (PASSING/RUSHING/RECEIVING/...), the second row is the
real header, where every <th> carries a semantic `data-id` attribute
(e.g. data-id="pass_cmp") -- that attribute, not the visible header text,
is what this module keys off of, since it's stable across cosmetic label
changes. _HEADER_MAP_BY_POSITION below renames each data-id to the exact
CSV header name the existing manual-upload files already use (cross-
checked against real files in data/nfl/2025/weekly_stats_*_week15.csv),
so parse_weekly_stats_html's output is byte-for-byte compatible with
parse_weekly_stats_csv (weekly_stats_loader.py) and with a manual upload
of the same week. WR and TE share an identical column set on the site.
"""

from __future__ import annotations

import csv
import io

import requests
from bs4 import BeautifulSoup

from backend.config import settings
from backend.repositories.dk_players.weekly_stats_repo import Position

_LEADERS_URL = "https://fantasydata.com/nfl/fantasy-football-leaders"

# Same defensive header set as the other scrapers in this app (see
# main_slate_scraper.py) -- requests' default User-Agent is a common
# trigger for stale/cached or bot-walled responses.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

_COMMON_HEADER_MAP: dict[str, str] = {
    "rank": "RK",
    "player": "NAME",
    "team": "TEAM",
    "pos": "POS",
    "game.week": "WK",
    "opp": "OPP",
}

_QB_HEADER_MAP: dict[str, str] = {
    **_COMMON_HEADER_MAP,
    "pass_cmp": "PASSING_CMP",
    "pass_att": "PASSING_ATT",
    "pass_cmp_pct": "PASSING_CMP%",
    "pass_yds": "PASSING_YDS",
    "pass_yds_per_att": "PASSING_AVG",
    "pass_td": "PASSING_TD",
    "pass_int": "INT",
    "pass_long": "LONG",
    "pass_sck": "SCK",
    "pass_rating": "RATING",
    "rush_att": "RUSHING_ATT",
    "rush_yds": "RUSHING_YDS",
    "rush_yds_per_att": "RUSHING_AVG",
    "rush_td": "RUSHING_TD",
    "fpts_ppr": "FPTS",
}

_RB_HEADER_MAP: dict[str, str] = {
    **_COMMON_HEADER_MAP,
    "rush_att": "RUSHING_ATT",
    "rush_yds": "RUSHING_YDS",
    "rush_yds_per_att": "RUSHING_AVG",
    "rush_td": "RUSHING_TD",
    "rec_tgt": "RECEIVING_TGTS",
    "rec": "RECEIVING_REC",
    "rec_yds": "RECEIVING_YDS",
    "rec_td": "RECEIVING_TD",
    "fum": "FUMBLES",
    "fum_lost": "FUMBLES_LOST",
    "fpts_ppr": "FPTS",
}

# WR and TE render an identical column set on the site (confirmed by
# comparing their data-id lists directly), and their real saved-file
# headers already match each other too.
_WR_TE_HEADER_MAP: dict[str, str] = {
    **_COMMON_HEADER_MAP,
    "rec_tgt": "RECEIVING_TGTS",
    "rec": "RECEIVING_REC",
    "catch_rate": "CATCH%",
    "rec_yds": "RECEIVING_YDS",
    "rec_td": "RECEIVING_TD",
    "rec_long": "LONG",
    "rec_yds_per_tgt": "YDS/TGT",
    "rec_yds_per_rec": "YDS/REC",
    "rush_att": "RUSHING_ATT",
    "rush_yds": "RUSHING_YDS",
    "rush_yds_per_att": "RUSHING_AVG",
    "rush_td": "RUSHING_TD",
    "fum": "FUMBLES",
    "fum_lost": "FUMBLES_LOST",
    "fpts_ppr": "FPTS",
}

_HEADER_MAP_BY_POSITION: dict[Position, dict[str, str]] = {
    "QB": _QB_HEADER_MAP,
    "RB": _RB_HEADER_MAP,
    "WR": _WR_TE_HEADER_MAP,
    "TE": _WR_TE_HEADER_MAP,
}

# Output column order per position -- must match the real manual-upload
# files' header order exactly. Doubles as the data-id read-order used
# when parsing each <tr> (looked up by index_by_id, not assumed to match
# the page's own left-to-right order, even though it has for every
# position checked so far).
_COLUMN_ORDER_BY_POSITION: dict[Position, list[str]] = {
    "QB": [
        "rank", "player", "team", "pos", "game.week", "opp",
        "pass_cmp", "pass_att", "pass_cmp_pct", "pass_yds", "pass_yds_per_att",
        "pass_td", "pass_int", "pass_long", "pass_sck", "pass_rating",
        "rush_att", "rush_yds", "rush_yds_per_att", "rush_td", "fpts_ppr",
    ],
    "RB": [
        "rank", "player", "team", "pos", "game.week", "opp",
        "rush_att", "rush_yds", "rush_yds_per_att", "rush_td",
        "rec_tgt", "rec", "rec_yds", "rec_td", "fum", "fum_lost", "fpts_ppr",
    ],
    "WR": [
        "rank", "player", "team", "pos", "game.week", "opp",
        "rec_tgt", "rec", "catch_rate", "rec_yds", "rec_td", "rec_long",
        "rec_yds_per_tgt", "rec_yds_per_rec",
        "rush_att", "rush_yds", "rush_yds_per_att", "rush_td",
        "fum", "fum_lost", "fpts_ppr",
    ],
    "TE": [
        "rank", "player", "team", "pos", "game.week", "opp",
        "rec_tgt", "rec", "catch_rate", "rec_yds", "rec_td", "rec_long",
        "rec_yds_per_tgt", "rec_yds_per_rec",
        "rush_att", "rush_yds", "rush_yds_per_att", "rush_td",
        "fum", "fum_lost", "fpts_ppr",
    ],
}


class WeeklyStatsScrapeError(Exception):
    """Raised when a position's leaders page can't be fetched or parsed
    into the expected table shape (e.g. FantasyData changed their
    markup) -- callers turn this into a per-position error message rather
    than failing every other position's scrape too."""


def _build_url(season: int, week: int, position: Position) -> str:
    return (
        f"{_LEADERS_URL}?scope=game&sp={season}_REG&week_from={week}&week_to={week}"
        f"&position={position.lower()}&scoring=fpts_ppr&pivot=0&order_by=fpts_ppr&sort_dir=desc"
    )


def fetch_weekly_stats_html(season: int, week: int, position: Position) -> str:
    """Fetches the raw leaders page HTML for one position/week. No login
    or session state needed -- see this module's docstring."""
    url = _build_url(season, week, position)
    response = requests.get(url, headers=_BROWSER_HEADERS, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    return response.text


def parse_weekly_stats_html(html: str, position: Position) -> str:
    """Parses one position's leaders page HTML into CSV text in the exact
    header/column shape the existing manual-upload files use (see
    weekly_stats_loader.py's parse_weekly_stats_csv). Raises
    WeeklyStatsScrapeError if the page doesn't have the expected table/
    header structure -- e.g. FantasyData changed their markup, or the
    page came back as a login/paywall wall instead of the real table."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.stats")
    if table is None:
        raise WeeklyStatsScrapeError(
            "Couldn't find the stats table on the page -- site structure may have changed"
        )

    header_rows = table.select("thead tr")
    if len(header_rows) < 2:
        raise WeeklyStatsScrapeError("Stats table header didn't have the expected two rows")

    data_ids = [th.get("data-id") for th in header_rows[1].select("th")]
    column_order = _COLUMN_ORDER_BY_POSITION[position]
    header_map = _HEADER_MAP_BY_POSITION[position]

    index_by_id = {data_id: i for i, data_id in enumerate(data_ids) if data_id}
    missing = [data_id for data_id in column_order if data_id not in index_by_id]
    if missing:
        raise WeeklyStatsScrapeError(
            f"Stats table is missing expected column(s) {missing} -- site structure may have changed"
        )

    body_rows = table.select("tbody tr")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([header_map[data_id] for data_id in column_order])
    for row in body_rows:
        cells = row.select("td")
        values = [
            cells[index_by_id[data_id]].get_text(strip=True) if index_by_id[data_id] < len(cells) else ""
            for data_id in column_order
        ]
        writer.writerow(values)

    return buffer.getvalue()


def scrape_weekly_stats_csv(season: int, week: int, position: Position) -> str:
    """Orchestrates fetch -> parse for one position. Callers are
    responsible for persisting the result (save_weekly_stats_csv) --
    mirrors scrape_main_slate's fetch/parse split, minus the login step
    this page doesn't need."""
    html = fetch_weekly_stats_html(season, week, position)
    return parse_weekly_stats_html(html, position)
