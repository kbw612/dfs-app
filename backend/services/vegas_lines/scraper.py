"""
Scrapes oneweekseason.com's public "Week N Matchups" page (e.g.
https://oneweekseason.com/week/week-1-2026/) for that (season, week)'s
per-game Vegas-line data -- kickoff time, both teams' names, each team's
implied total, and the game's over/under. See backend/schemas/
vegas_lines/vegas_lines.py for how a raw scrape here becomes a
VegasLinesSnapshot (this module only fetches + parses; merging into
"initial" vs "current" happens in backend/services/vegas_lines/merge.py).

Formerly lived at backend/services/game_environment/scraper.py and wrote
straight into GameEnvironmentEntry -- moved and reshaped once Vegas Lines
became its own browsable resource rather than a direct pipe into scoring.

No login required for this page -- confirmed by fetching it directly
before writing this module, unlike Ownership's scrape of the same site
(backend/services/ownership/scraper.py). So there's no username/password
handling here at all.

Each game is one <article class="ows-game"> block, containing:

    <h6>Kickoff Wednesday, Sep 9th 8:20pm Eastern</h6>
    <h1 class="page-title hero">
      <a href="...">Patriots <small>(<div class="team-colors" .../> 20.5) at</small>
      <br> Hawks <small>(<div class="team-colors" .../> 24)</small></a>
    </h1>
    <h4 class="over-under">Over/Under 44.5</h4>

The h6's leading "Kickoff" word is stripped when building kickoff_label
below -- the UI already labels this as the kickoff time, so the field
itself is just "Wednesday, Sep 9th 8:20pm Eastern".

The h1's plain text (team-colors divs contribute none) normalizes to
"Patriots ( 20.5) at Hawks ( 24)" -- "X at Y" is standard sports-page
phrasing for "X (away) is playing at Y's (home) stadium", so the first
team is away and the second is home; this matches OwnershipPlayer's own
is_home semantics elsewhere in the app.

The page uses each team's short nickname ("Hawks", "WFT", "Cards", "Bucs")
rather than this app's abbreviations, so _TEAM_ALIASES below maps every
current NFL team's nickname (plus a couple of common alternate spellings)
to the abbreviation used everywhere else in this app (config/team-info.csv).
Unlike the old game_environment scraper, a name that doesn't match
anything in that table does NOT get skipped here -- the game still comes
back (with away_team/home_team/game_key left None) since Vegas Lines is a
browse view of the raw scrape, not a direct write into scoring; only the
apply step (backend/api/vegas_lines/apply.py) needs a resolved game_key,
and it skips unresolved games itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from backend.config import settings

# oneweekseason.com's own short nickname for each team -> this app's
# abbreviation (config/team-info.csv). Keyed lowercase; a couple of
# alternate spellings are included defensively in case a different week's
# page (or a future site redesign) uses a slightly different nickname than
# Week 1 2026 did.
_TEAM_ALIASES: dict[str, str] = {
    "cardinals": "ARI", "cards": "ARI",
    "falcons": "ATL",
    "ravens": "BAL",
    "bills": "BUF",
    "panthers": "CAR",
    "bears": "CHI",
    "bengals": "CIN",
    "browns": "CLE",
    "cowboys": "DAL",
    "broncos": "DEN",
    "lions": "DET",
    "packers": "GB",
    "texans": "HOU",
    "colts": "IND",
    "jaguars": "JAX", "jags": "JAX",
    "chiefs": "KC",
    "chargers": "LAC",
    "rams": "LAR",
    "raiders": "LV",
    "dolphins": "MIA",
    "vikings": "MIN",
    "patriots": "NE",
    "saints": "NO",
    "giants": "NYG",
    "jets": "NYJ",
    "eagles": "PHI",
    "steelers": "PIT",
    "49ers": "SF", "niners": "SF",
    "seahawks": "SEA", "hawks": "SEA",
    "buccaneers": "TB", "bucs": "TB",
    "titans": "TEN",
    "commanders": "WAS", "wft": "WAS", "washington": "WAS",
}

# requests' default User-Agent is a common trigger for stale/cached or
# bot-walled responses -- same defensive header set as depth_charts/
# scraper.py's _BROWSER_HEADERS, applied here too even though this page
# hasn't shown that symptom yet.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

_MATCHUP_RE = re.compile(
    r"^(?P<away>.+?)\s*\(\s*(?P<away_total>[\d.]+)\)\s*at\s*(?P<home>.+?)\s*\(\s*(?P<home_total>[\d.]+)\)$",
    re.IGNORECASE,
)
_OVER_UNDER_RE = re.compile(r"([\d.]+)")


def resolve_team_abbrev(name: str) -> str | None:
    return _TEAM_ALIASES.get(name.strip().lower())


def _game_key(home_abbrev: str, away_abbrev: str) -> str:
    """Alphabetically-sorted "TEAM1-TEAM2", matching the convention used
    everywhere else a game is keyed in this app (see backend/services/
    player_pool/engine.py's game_id and backend/schemas/game_environment/
    game_environment.py's game_key docstring) -- not an away/home order
    despite that docstring's example."""
    return "-".join(sorted([home_abbrev, away_abbrev]))


@dataclass
class ScrapedGame:
    """One game block's raw scrape -- transient output of parse_games(),
    not persisted directly (see merge.py for how this becomes part of a
    saved VegasLinesSnapshot)."""

    away_name: str
    home_name: str
    away_team: str | None
    home_team: str | None
    game_key: str | None
    kickoff_label: str | None
    over_under: float | None
    home_implied_total: float
    away_implied_total: float


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=_BROWSER_HEADERS, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    return response.text


def parse_games(html: str) -> tuple[list[ScrapedGame], list[str]]:
    """Every game block this page's HTML parses cleanly into a
    ScrapedGame, plus human-readable messages for any block that didn't
    (missing heading or unparseable matchup text) -- those are skipped
    rather than raising, so one odd block doesn't fail the whole scrape.
    An unresolved team name is NOT a skip reason here (see this module's
    docstring) -- only a missing/unparseable heading is."""
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article.ows-game")

    games: list[ScrapedGame] = []
    messages: list[str] = []
    if not articles:
        messages.append("No game blocks found on the page -- page structure may have changed")

    for article in articles:
        heading = article.select_one("h1.page-title")
        over_under_tag = article.select_one("h4.over-under")
        kickoff_tag = article.select_one("h6")
        if heading is None:
            messages.append("Skipped a game block with no matchup heading")
            continue

        matchup_text = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
        match = _MATCHUP_RE.match(matchup_text)
        if match is None:
            messages.append(f"Couldn't parse matchup text: {matchup_text!r}")
            continue

        away_name, away_total, home_name, home_total = (
            match.group("away"), match.group("away_total"), match.group("home"), match.group("home_total")
        )
        away_abbrev = resolve_team_abbrev(away_name)
        home_abbrev = resolve_team_abbrev(home_name)
        if away_abbrev is None or home_abbrev is None:
            messages.append(f"Unrecognized team name(s) in {matchup_text!r} -- shown but can't be applied yet")

        over_under = None
        if over_under_tag is not None:
            ou_match = _OVER_UNDER_RE.search(over_under_tag.get_text(strip=True))
            over_under = float(ou_match.group(1)) if ou_match else None

        kickoff_label = None
        if kickoff_tag is not None:
            kickoff_label = re.sub(r"^\s*Kickoff\s*", "", kickoff_tag.get_text(strip=True), flags=re.IGNORECASE)

        games.append(
            ScrapedGame(
                away_name=away_name,
                home_name=home_name,
                away_team=away_abbrev,
                home_team=home_abbrev,
                game_key=_game_key(home_abbrev, away_abbrev) if away_abbrev and home_abbrev else None,
                kickoff_label=kickoff_label,
                over_under=over_under,
                home_implied_total=float(home_total),
                away_implied_total=float(away_total),
            )
        )

    return games, messages


def scrape(season: int, week: int) -> tuple[list[ScrapedGame], list[str]]:
    """Orchestrates fetch -> parse for this (season, week). Callers are
    responsible for merging/persisting the result (see backend/api/
    vegas_lines/scrape.py and backend/services/vegas_lines/merge.py) --
    this function has no side effects of its own."""
    url = settings.oneweekseason_week_url_template.format(season=season, week=week)
    html = fetch_html(url)
    return parse_games(html)
