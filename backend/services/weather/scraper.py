"""
Scrapes mysportsweather.com/nfl's public "Kevin's note" cards -- a color
classification plus free-text commentary, for whichever games a
meteorologist ("Kevin") flagged as having notable game-day weather. See
backend/schemas/weather/weather.py for how a raw scrape here becomes a
WeatherSnapshot (this module only fetches + parses; there's no merge step
the way Vegas Lines has one, since the source only ever shows "this week").

No login required for this page -- confirmed by fetching it directly
before writing this module.

The page also has a detailed per-game hourly forecast table (temp/precip/
wind by hour) for every game -- this is deliberately NOT scraped. Only the
note cards are, per the Weather tab's own scope (color + commentary only,
nothing else from this source, at least for now).

Each note is one <div class="mlb-writeup mlb-writeup--{color}"> block:

    <div class="mlb-writeup mlb-writeup--yellow">
      <div class="mlb-writeup__header">
        <span class="mlb-writeup__matchup">New Orleans Saints at Baltimore Ravens · Kevin's note</span>
        <span class="mlb-writeup__time">1:00 PM ET</span>
      </div>
      <div class="mlb-writeup__body">There's certainly rain around, ...</div>
    </div>

Not every game gets one of these -- only the subset with notable weather
(confirmed live: 7 of 15 games in a typical week). Games without a note
simply have no matching div and never appear in parse_notes()'s output.

The matchup span's "X at Y" phrasing is the same away-at-home convention
used by vegas_lines/scraper.py's page. Team names here are the full name
("Baltimore Ravens"), which matches config/team-info.csv's "Full Name"
column exactly -- unlike Vegas Lines' nickname-based source, no separate
alias table is needed; backend/services/depth_charts/enrich.py's
load_team_abbrev_map() is reused directly.

The color is read straight off the mlb-writeup--{color} class suffix and
passed through as an arbitrary string rather than validated against a
fixed set -- Kevin's site is the source of truth for what colors exist
(only yellow/orange/green have been observed so far, but red is plausible
for more severe weather and should come through unmodified if/when it
appears, not be dropped for being unrecognized).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from backend.config import settings
from backend.services.depth_charts.enrich import load_team_abbrev_map

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

_COLOR_CLASS_RE = re.compile(r"^mlb-writeup--(.+)$")
_MATCHUP_SUFFIX_RE = re.compile(r"\s*·\s*Kevin's note\s*$", re.IGNORECASE)


def resolve_team_abbrev(name: str, abbrev_by_full_name: dict[str, str]) -> str | None:
    return abbrev_by_full_name.get(name.strip())


def _game_key(home_abbrev: str, away_abbrev: str) -> str:
    """Alphabetically-sorted "TEAM1-TEAM2", matching the convention used
    everywhere else a game is keyed in this app."""
    return "-".join(sorted([home_abbrev, away_abbrev]))


@dataclass
class ScrapedWeatherNote:
    """One note card's raw scrape -- transient output of parse_notes(),
    not persisted directly (see backend/api/weather/scrape.py for how this
    becomes a saved WeatherSnapshot)."""

    away_name: str
    home_name: str
    away_team: str | None
    home_team: str | None
    game_key: str | None
    kickoff_label: str | None
    color: str
    note: str


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=_BROWSER_HEADERS, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    return response.text


def parse_notes(html: str, abbrev_by_full_name: dict[str, str]) -> tuple[list[ScrapedWeatherNote], list[str]]:
    """Every note card this page's HTML parses cleanly into a
    ScrapedWeatherNote, plus human-readable messages for any block that
    didn't (missing matchup heading, unparseable matchup text, or a class
    with no color suffix) -- those are skipped rather than raising, so one
    odd block doesn't fail the whole scrape. An unresolved team name is
    NOT a skip reason (same rationale as vegas_lines/scraper.py) -- the
    note still comes back with away_team/home_team/game_key left None."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.mlb-writeup")

    notes: list[ScrapedWeatherNote] = []
    messages: list[str] = []
    if not cards:
        messages.append("No weather note cards found on the page -- page structure may have changed")

    for card in cards:
        color = None
        for cls in card.get("class", []):
            match = _COLOR_CLASS_RE.match(cls)
            if match:
                color = match.group(1)
                break
        if color is None:
            messages.append("Skipped a note card with no color class")
            continue

        matchup_tag = card.select_one(".mlb-writeup__matchup")
        body_tag = card.select_one(".mlb-writeup__body")
        time_tag = card.select_one(".mlb-writeup__time")

        if matchup_tag is None or body_tag is None:
            messages.append(f"Skipped a {color!r} note card missing its matchup or body text")
            continue

        matchup_text = _MATCHUP_SUFFIX_RE.sub("", matchup_tag.get_text(" ", strip=True)).strip()
        if " at " not in matchup_text:
            messages.append(f"Couldn't parse matchup text: {matchup_text!r}")
            continue
        away_name, home_name = matchup_text.split(" at ", 1)
        away_name, home_name = away_name.strip(), home_name.strip()

        away_abbrev = resolve_team_abbrev(away_name, abbrev_by_full_name)
        home_abbrev = resolve_team_abbrev(home_name, abbrev_by_full_name)
        if away_abbrev is None or home_abbrev is None:
            messages.append(f"Unrecognized team name(s) in {matchup_text!r} -- shown but can't be matched to a game")

        notes.append(
            ScrapedWeatherNote(
                away_name=away_name,
                home_name=home_name,
                away_team=away_abbrev,
                home_team=home_abbrev,
                game_key=_game_key(home_abbrev, away_abbrev) if away_abbrev and home_abbrev else None,
                kickoff_label=time_tag.get_text(strip=True) if time_tag else None,
                color=color,
                note=body_tag.get_text(" ", strip=True),
            )
        )

    return notes, messages


def scrape() -> tuple[list[ScrapedWeatherNote], list[str]]:
    """Orchestrates fetch -> parse for whatever's currently on the page --
    unlike vegas_lines' scrape(), there's no (season, week) URL parameter
    since the source only ever shows the current week. Callers attach
    (season, week) themselves when saving the result (see backend/api/
    weather/scrape.py); this function has no side effects of its own."""
    abbrev_by_full_name = load_team_abbrev_map(settings.team_info_csv)
    html = fetch_html(settings.mysportsweather_nfl_url)
    return parse_notes(html, abbrev_by_full_name)
