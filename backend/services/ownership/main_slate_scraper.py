"""
Scrapes oneweekseason.com's public DraftKings Main Slate page
(https://oneweekseason.com/draftkings-main-slate/) for this week's
ownership/salary/projection table -- the "ALL" section covers every
position in one table, per the feature request this module was built for.

This page isn't reliably login-free: it was open to anonymous visitors in
Week 1 2026 (confirmed by fetching it with no session/cookies at all and
still getting the full table), but the site is expected to put it behind
a login in later weeks, same as Ownership's other scrape target
(scraper.py's /basic-ownership-dk, which has always required login). So
every fetch here goes through a session that logs in first *whenever
credentials are configured* (settings.ownership_source_username/
password, shared with that other scraper -- see site_login.py) --
harmless on a week where the page turns out to still be free, since an
authenticated session can read a public page just fine. If no credentials
are configured, the session just goes in anonymous, which is exactly what
worked for Week 1.

The page renders one <table> per position tab plus one covering all of
them; the all-positions table is the only one this module reads, uniquely
selectable via `table.ows-main-table--all` (the per-position tables share
the `ows-preview-table ows-main-table` classes but lack the `--all`
modifier). Its columns, in order, are:

    Player, Team, Pos, Opp, Salary, Proj., Ceiling, Own, Tm Own

This module preserves every column when building the CSV it hands back
(the app doesn't need Proj./Ceiling/Tm Own, but there's no reason to throw
them away -- see save_projections_csv's caller), renaming only the three
whose header name has to match what parse_ownership_projections_csv
(csv_loader.py) expects: Pos -> Position, Opp -> Opponent, Own -> %
ownership. Team/Opp values get the same LA-team-abbreviation fix
(normalize_team_abbrev) as every other ownership data path in this app,
defensively, even though this particular table hasn't been observed to
need it.

The page also displays which week's slate it's currently showing (a
"Week N" label near the top) -- extract_displayed_week() pulls that out so
the caller can refuse to save if the live site is showing a different week
than the app's currently-selected one (e.g. the site rolled over to a new
week's slate before the user switched the app's own week selector).
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable

import requests
from bs4 import BeautifulSoup

from backend.config import settings
from backend.schemas.depth_charts.snapshot import Message
from backend.services.ownership.parsing import UNDER_ONE_PCT, normalize_team_abbrev
from backend.services.ownership.site_login import login

# Same defensive header set as vegas_lines/scraper.py and depth_charts/
# scraper.py -- requests' default User-Agent is a common trigger for
# stale/cached or bot-walled responses.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Site header -> saved-CSV header. Only these three need renaming to match
# what parse_ownership_projections_csv expects; every other column is
# passed through with the site's own header text unchanged.
_HEADER_RENAMES = {
    "Pos": "Position",
    "Opp": "Opponent",
    "Own": "% ownership",
}

# Site columns whose values are team abbreviations -- normalized the same
# way as every other ownership data path (see parsing.py's docstring for
# the LA-team quirk this guards against).
_TEAM_ABBREV_COLUMNS = {"Team", "Opp"}

_WEEK_RE = re.compile(r"Week\s+(\d+)", re.IGNORECASE)

# The page's "Under 1% Owned" table (`ows-low-owned-table`) lists projected
# players the main table leaves out, every one shown as "<1%". They are saved
# at the UNDER_ONE_PCT placeholder (see parsing.py). It has no Tm Own column, and its Pos can be wrong (a PIT
# WR once came through as "LB"), so each row's position comes from the week's
# DK salary file when a lookup is given.
LOW_OWNED_PCT = f"{UNDER_ONE_PCT:g}%"  # placeholder for "<1%"
VALID_POSITIONS = {"QB", "RB", "WR", "TE", "DST"}

# (player name, team) -> DK position, from the week's salary file.
PositionLookup = Callable[[str, str], str | None]


def build_session() -> requests.Session:
    """A plain, anonymous session if no credentials are configured (this
    is what worked for Week 1, while the page was still free) -- otherwise
    logs in first using the same oneweekseason.com credentials the older
    /basic-ownership-dk scraper uses (settings.ownership_source_username/
    password), so this keeps working once the site puts the Main Slate
    page behind a login too. Login failure isn't detected here (see
    site_login.login's docstring) -- an unauthenticated session just won't
    find the table later, which scrape_main_slate() turns into a helpful
    message rather than a silent empty result."""
    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)
    if settings.ownership_source_username and settings.ownership_source_password:
        login(session, settings.ownership_source_url, settings.ownership_source_username, settings.ownership_source_password)
    return session


def fetch_main_slate_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    return response.text


def extract_displayed_week(html: str) -> int | None:
    """None if the page's markup doesn't contain a recognizable "Week N"
    label (e.g. a future site redesign) -- callers should treat that as
    "couldn't verify," not "week 0," and decide for themselves whether to
    proceed without the safety check."""
    soup = BeautifulSoup(html, "html.parser")
    preview = soup.select_one("section.ows-front-preview")
    text = preview.get_text(" ", strip=True) if preview is not None else soup.get_text(" ", strip=True)
    match = _WEEK_RE.search(text)
    return int(match.group(1)) if match else None


def parse_main_slate_csv(
    html: str, position_lookup: PositionLookup | None = None
) -> tuple[str | None, list[Message]]:
    """Builds raw CSV text (same shape save_projections_csv/
    parse_ownership_projections_csv expect, just with extra columns the
    app doesn't consume) from the page's all-positions table. Returns
    (None, [error]) if the table itself can't be found -- a row-level
    problem (too few cells) skips just that row with a warning rather than
    failing the whole scrape."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.ows-main-table--all:not(.ows-low-owned-table)")
    if table is None:
        return None, [
            Message(
                level="error",
                step="scrape-main-slate",
                message="Couldn't find the all-positions table on the page -- site structure may have changed",
            )
        ]

    header_cells = [th.get_text(strip=True) for th in table.select("thead th")]
    if not header_cells:
        first_row = table.select_one("tr")
        header_cells = [cell.get_text(strip=True) for cell in first_row.select("th, td")] if first_row else []
    if not header_cells:
        return None, [
            Message(level="error", step="scrape-main-slate", message="All-positions table has no header row")
        ]

    output_headers = [_HEADER_RENAMES.get(h, h) for h in header_cells]

    body_rows = table.select("tbody tr")
    if not body_rows:
        all_rows = table.select("tr")
        body_rows = all_rows[1:] if len(all_rows) > 1 else []

    messages: list[Message] = []
    csv_rows: list[list[str]] = []
    for row in body_rows:
        cells = row.select("td")
        if len(cells) != len(header_cells):
            player_name = cells[0].get_text(strip=True) if cells else "?"
            messages.append(
                Message(
                    level="warning",
                    step="scrape-main-slate",
                    message=f"Skipped a row with unexpected column count (player: {player_name!r})",
                )
            )
            continue

        values = [cell.get_text(strip=True) for cell in cells]
        for i, header in enumerate(header_cells):
            if header in _TEAM_ABBREV_COLUMNS:
                values[i] = normalize_team_abbrev(values[i])
        csv_rows.append(values)

    low_rows, low_messages = _parse_low_owned_rows(soup, header_cells, position_lookup)
    csv_rows.extend(low_rows)
    messages.extend(low_messages)

    if not csv_rows:
        messages.append(Message(level="warning", step="scrape-main-slate", message="No player rows parsed from table"))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(output_headers)
    writer.writerows(csv_rows)
    return buffer.getvalue(), messages


def _parse_low_owned_rows(
    soup: BeautifulSoup, header_cells: list[str], position_lookup: PositionLookup | None
) -> tuple[list[list[str]], list[Message]]:
    """Rows of the "Under 1% Owned" table, shaped like the main table's rows
    (same columns, missing ones such as Tm Own left blank), each at
    LOW_OWNED_PCT. The position is the salary file's when known, else the
    site's if it is a real DK position; otherwise the row is skipped with a
    warning. Text is read with textContent semantics (get_text) since the
    table can be hidden on the page."""
    table = soup.select_one("table.ows-low-owned-table")
    if table is None:
        return [], []

    low_headers = [th.get_text(strip=True).lower() for th in table.select("thead th")]
    messages: list[Message] = []
    rows: list[list[str]] = []
    fixed: list[str] = []
    for tr in table.select("tbody tr"):
        cells = [td.get_text(strip=True) for td in tr.select("td")]
        if len(cells) != len(low_headers):
            continue
        by_header = dict(zip(low_headers, cells))
        name = by_header.get("player", "")
        team = normalize_team_abbrev(by_header.get("team", ""))
        site_pos = by_header.get("pos", "").upper()

        position = (position_lookup(name, team) if position_lookup else None) or site_pos
        if position not in VALID_POSITIONS:
            messages.append(
                Message(
                    level="warning",
                    step="scrape-main-slate",
                    message=f"Skipped {name!r} ({team}): position {site_pos!r} isn't a DraftKings position and wasn't found in the salary file",
                )
            )
            continue
        if position != site_pos:
            fixed.append(f"{name} {site_pos}\u2192{position}")

        out = []
        for header in header_cells:
            key = header.lower()
            if key == "pos":
                out.append(position)
            elif key == "own":
                out.append(LOW_OWNED_PCT)
            elif key in ("team", "opp"):
                out.append(normalize_team_abbrev(by_header.get(key, "")))
            else:
                out.append(by_header.get(key, ""))
        rows.append(out)

    if fixed:
        messages.append(
            Message(
                level="info",
                step="scrape-main-slate",
                message="Under-1% players given their salary-file position: " + ", ".join(fixed),
            )
        )
    return rows, messages


def scrape_main_slate(
    url: str, position_lookup: PositionLookup | None = None
) -> tuple[str | None, int | None, list[Message]]:
    """Orchestrates login (if configured) -> fetch -> parse for the main
    slate page. Callers are responsible for the week cross-check and for
    persisting the result (see backend/api/ownership/scrape_main_slate.py)
    -- this function has no side effects of its own beyond the login
    itself."""
    session = build_session()
    html = fetch_main_slate_html(session, url)
    displayed_week = extract_displayed_week(html)
    csv_text, messages = parse_main_slate_csv(html, position_lookup)

    if csv_text is None:
        has_credentials = bool(settings.ownership_source_username and settings.ownership_source_password)
        hint = (
            "Logged in with the configured OWS credentials but still couldn't find the table -- "
            "double-check DFS_APP_OWNERSHIP_SOURCE_USERNAME/PASSWORD, or the page structure may have changed."
            if has_credentials
            else "No OWS login is configured -- if the site now requires login for this page, set "
            "DFS_APP_OWNERSHIP_SOURCE_USERNAME and DFS_APP_OWNERSHIP_SOURCE_PASSWORD (env or .env) and try again."
        )
        messages.append(Message(level="error", step="scrape-main-slate", message=hint))

    return csv_text, displayed_week, messages
