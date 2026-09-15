"""
Ownership scraper -- DK salary/ownership projections, scraped from
oneweekseason.com (a login-gated site) for a single (season, week).
Ported from the uploaded high_owned_players.py notebook, with three
changes: session-based login via `requests` instead of `mechanize` (one
less dependency, and this app already uses requests everywhere else --
see depth_charts/scraper.py), credentials pulled from
settings.ownership_source_username/password (env-only, never hardcoded)
instead of a literal email/password in source, and DST kept in the same
flat player list instead of being split into a second file (it's still
just a `position` value like any other).

login() itself now lives in site_login.py, shared with
main_slate_scraper.py (the DraftKings Main Slate page, which didn't used
to need login but the site switches on later in the week) -- re-exported
here so nothing importing `backend.services.ownership.scraper.login`
breaks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from backend.config import settings
from backend.schemas.depth_charts.snapshot import Message
from backend.schemas.ownership.ownership import OwnershipPlayer, OwnershipSnapshot
from backend.services.ownership.parsing import normalize_team_abbrev, parse_opponent, parse_ownership_pct, parse_salary
from backend.services.ownership.site_login import login  # noqa: F401

_OWNERSHIP_PATH = "/basic-ownership-dk"
_OWNERSHIP_TABLE_ID = "table_1"


def fetch_ownership_html(session: requests.Session, base_url: str) -> str:
    url = urljoin(base_url, _OWNERSHIP_PATH)
    response = session.get(url, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    return response.text


def parse_players(html: str) -> tuple[list[OwnershipPlayer], list[Message]]:
    """Parses the scraped HTML into OwnershipPlayer rows, plus any
    scrape-level messages worth surfacing (missing table -- most likely a
    failed login -- or individual unparseable rows, which are skipped
    rather than aborting the whole scrape)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=_OWNERSHIP_TABLE_ID)

    messages: list[Message] = []
    if table is None:
        messages.append(
            Message(
                level="error",
                step="scrape",
                message=(
                    f"Table id='{_OWNERSHIP_TABLE_ID}' not found -- login likely failed, "
                    "or the page structure changed"
                ),
            )
        )
        return [], messages

    players: list[OwnershipPlayer] = []
    for row in table.find_all("tr")[1:]:  # skip header row
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        player = cells[0].get_text(strip=True)
        position = cells[1].get_text(strip=True)
        team = normalize_team_abbrev(cells[2].get_text(strip=True))
        opponent, is_home = parse_opponent(cells[3].get_text(strip=True))

        try:
            salary = parse_salary(cells[4].get_text(strip=True))
            ownership_pct = parse_ownership_pct(cells[5].get_text(strip=True))
        except ValueError:
            messages.append(
                Message(
                    level="warning",
                    step="scrape",
                    message=f"Couldn't parse salary/ownership for {player!r} -- row skipped",
                )
            )
            continue

        players.append(
            OwnershipPlayer(
                player=player,
                position=position,
                team=team,
                opponent=opponent,
                is_home=is_home,
                salary=salary,
                ownership_pct=ownership_pct,
            )
        )

    if not players:
        messages.append(
            Message(level="warning", step="scrape", message="Ownership table found but had no rows")
        )

    return players, messages


def scrape(season: int, week: int) -> tuple[OwnershipSnapshot, list[Message]]:
    """Orchestrates login -> fetch -> parse -> build for one (season,
    week). Raises ValueError if credentials aren't configured -- see
    settings.ownership_source_username/password."""
    if not settings.ownership_source_username or not settings.ownership_source_password:
        raise ValueError(
            "DFS_APP_OWNERSHIP_SOURCE_USERNAME/PASSWORD must be set (env or .env) to scrape ownership data"
        )

    session = requests.Session()
    login(
        session,
        settings.ownership_source_url,
        settings.ownership_source_username,
        settings.ownership_source_password,
    )
    html = fetch_ownership_html(session, settings.ownership_source_url)
    players, messages = parse_players(html)

    snapshot = OwnershipSnapshot(
        scraped_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        source_url=urljoin(settings.ownership_source_url, _OWNERSHIP_PATH),
        season=season,
        week=week,
        players=players,
    )
    return snapshot, messages
