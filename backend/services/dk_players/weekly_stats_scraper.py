"""
Scrapes FantasyData.com's public "Fantasy Football Leaders" page
(https://fantasydata.com/nfl/fantasy-football-leaders) for one week's
QB/RB/WR/TE/DST game-log stats -- the same 5 files Settings' Weekly Stats
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
&position={qb|rb|wr|te|dst}&scoring=fpts_ppr&pivot=0&order_by=fpts_ppr
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

DST is structurally different from the other four: its table has no
"player"/"pos"/"rank" columns at all (a defense's row is identified by
TEAM alone), so parse_weekly_stats_html synthesizes RK (row position),
NAME (converted to DK's own bare-nickname DST naming, e.g. "Chargers",
via resolve_team_nickname), and POS ("DST" literal) rather than reading
them off any data-id -- see _DST_HEADER_MAP's own comment for why it
doesn't reuse _COMMON_HEADER_MAP the way every other position does.

DST's own "team" data-id cell is ALSO structurally different from every
other position's: QB/RB/WR/TE render their TEAM cell as a plain
abbreviation ("BUF"), but DST's own TEAM cell renders the team's full
name as link text ("Cincinnati Bengals", linking to that team's schedule
page) -- confirmed empirically, not documented anywhere on the site. So
the DST branch below runs that cell's text through
load_team_abbrev_map(settings.team_info_csv)'s {full_name: abbrev} map
first, to recover the real abbreviation for both the TEAM output column
and the NAME-via-resolve_team_nickname lookup -- resolve_team_nickname
expects an abbreviation, not a full name, so skipping this step is what
silently produced garbage NAME/TEAM values (the literal full-name string)
the first time this was scraped.
"""

from __future__ import annotations

import csv
import io

import requests
from bs4 import BeautifulSoup

from backend.config import settings
from backend.repositories.dk_players.weekly_stats_repo import Position
from backend.services.depth_charts.enrich import load_team_abbrev_map
from backend.services.shared.team_names import resolve_team_nickname

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

# DST's leaders table has no "player"/"pos" columns at all -- a defense's
# page-of-record row is keyed by TEAM alone, with no per-player rank/name.
# So this map (unlike the other four) intentionally does NOT reuse
# _COMMON_HEADER_MAP -- "team" is the only column shared with it, and
# "rank"/"player"/"pos" are synthesized in parse_weekly_stats_html itself
# (RK from row position, NAME from TEAM via resolve_team_nickname, POS
# hardcoded to "DST") rather than read off any data-id.
#
# DEF_SCK/DEF_INT (not "SCK"/"INT") deliberately, even though the site's
# own headers/the user's requested field names are "SCK"/"INT" -- QB's own
# file already has a "SCK" column (sacks *taken* by the QB) and an "INT"
# column (passes *thrown* intercepted), and weekly_stats_loader.py's
# column-presence-based parsing (`if column in row`) runs the same generic
# column maps over every position's file. Reusing "SCK"/"INT" for DST's
# very different "sacks/interceptions *recorded*" stats would silently
# collide with QB's columns of the same name. The frontend is free to
# still label these "SCK"/"INT" -- this is a storage-layer disambiguation
# only, invisible to the API/UI.
_DST_HEADER_MAP: dict[str, str] = {
    "team": "TEAM",
    "game.week": "WK",
    "opp": "OPP",
    "tkl_loss": "LOSS",
    "def_sck": "DEF_SCK",
    "qb_hits": "QB_HITS",
    "def_int": "DEF_INT",
    "fum_recovered": "FR",
    "safeties": "SFTY",
    "def_td": "DEF_TD",
    "return_td": "RET_TD",
    "opp_pts": "OPP_PTS",
    "fpts_ppr": "FPTS",
}

_HEADER_MAP_BY_POSITION: dict[Position, dict[str, str]] = {
    "QB": _QB_HEADER_MAP,
    "RB": _RB_HEADER_MAP,
    "WR": _WR_TE_HEADER_MAP,
    "TE": _WR_TE_HEADER_MAP,
    "DST": _DST_HEADER_MAP,
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
    # No "rank"/"player"/"pos" data-ids here -- see _DST_HEADER_MAP's comment.
    "DST": [
        "team", "game.week", "opp", "tkl_loss", "def_sck", "qb_hits",
        "def_int", "fum_recovered", "safeties", "def_td", "return_td",
        "opp_pts", "fpts_ppr",
    ],
}

# The real, saved-file-compatible header order for DST -- RK/NAME/POS are
# synthesized (see _DST_HEADER_MAP's comment), everything else follows
# _COLUMN_ORDER_BY_POSITION["DST"] via _DST_HEADER_MAP.
_DST_OUTPUT_HEADER: list[str] = [
    "RK", "NAME", "TEAM", "POS", "WK", "OPP", "LOSS", "DEF_SCK", "QB_HITS",
    "DEF_INT", "FR", "SFTY", "DEF_TD", "RET_TD", "OPP_PTS", "FPTS",
]


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

    # DST's page has a single thead row (no PASSING/RUSHING/RECEIVING-style
    # group-label row above it, since DST has no stat-category groupings) --
    # QB/RB/WR/TE have two. The real per-column data-id header is always the
    # LAST thead row regardless of how many rows precede it, so grab that
    # rather than hardcoding an index that only holds for the 2-row case.
    header_rows = table.select("thead tr")
    if len(header_rows) < 1:
        raise WeeklyStatsScrapeError("Stats table header didn't have any rows")

    data_ids = [th.get("data-id") for th in header_rows[-1].select("th")]
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

    if position == "DST":
        # RK/NAME/POS aren't real columns on this page -- RK is just this
        # row's position in the (already FPTS-sorted) table, NAME is
        # derived from TEAM so it matches the DK Players tracker's own
        # bare-nickname DST naming (see resolve_team_nickname's docstring),
        # and POS is always "DST". An unresolved TEAM value falls back to
        # itself rather than failing the whole scrape -- same tolerant-row
        # philosophy as vegas_lines/scraper.py.
        #
        # DST's own "team" cell text is the team's FULL name ("Cincinnati
        # Bengals"), not an abbreviation like every other position's TEAM
        # cell -- see this module's own docstring. team_abbrev_by_full_name
        # recovers the real abbreviation before resolve_team_nickname (which
        # expects an abbreviation) ever sees it.
        team_abbrev_by_full_name = load_team_abbrev_map(settings.team_info_csv)
        writer.writerow(_DST_OUTPUT_HEADER)
        for rank, row in enumerate(body_rows, start=1):
            cells = row.select("td")

            def cell(data_id: str) -> str:
                i = index_by_id[data_id]
                return cells[i].get_text(strip=True) if i < len(cells) else ""

            team_full_name = cell("team")
            team_abbrev = team_abbrev_by_full_name.get(team_full_name, team_full_name)
            name = resolve_team_nickname(team_abbrev) or team_abbrev
            writer.writerow(
                [
                    rank, name, team_abbrev, "DST", cell("game.week"), cell("opp"),
                    cell("tkl_loss"), cell("def_sck"), cell("qb_hits"), cell("def_int"),
                    cell("fum_recovered"), cell("safeties"), cell("def_td"),
                    cell("return_td"), cell("opp_pts"), cell("fpts_ppr"),
                ]
            )
        return buffer.getvalue()

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
