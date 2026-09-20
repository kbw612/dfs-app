"""
Weather: the raw per-game scrape of mysportsweather.com/nfl's "Kevin's
note" cards (backend/services/weather/scraper.py) -- a color classification
plus free-text commentary, for whichever games the meteorologist flagged as
having notable game-day weather. Unlike Vegas Lines, there's no separate
"initial" vs "current" here -- the site only ever shows the current week's
forecast, so a re-scrape just replaces the prior snapshot outright (no
drift-tracking concept applies).

Only games with a note are ever included here (see the Weather tab's own
design: the other per-hour forecast detail on the source page isn't scraped
at all -- just this signal). A game with no notable weather simply never
appears in `games`, for any (season, week).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class WeatherGame(BaseModel):
    # Exactly as scraped, e.g. "New Orleans Saints" / "Baltimore Ravens" --
    # for display. Not necessarily this app's team abbreviation (see
    # away_team/home_team).
    away_name: str
    home_name: str
    # This app's abbreviation, resolved via config/team-info.csv's Full
    # Name column (the source site already uses full team names, so no
    # separate alias table is needed the way Vegas Lines' nickname-based
    # source required one) -- None if away_name/home_name didn't match.
    away_team: Optional[str] = None
    home_team: Optional[str] = None
    # Alphabetically-sorted "TEAM1-TEAM2", same convention as everywhere
    # else a game is keyed in this app -- None whenever either team didn't
    # resolve (nothing stable to key on yet).
    game_key: Optional[str] = None
    # Verbatim scraped kickoff line, e.g. "1:00 PM ET" -- display only.
    kickoff_label: Optional[str] = None
    # The raw CSS modifier suffix off the note's "mlb-writeup--{color}"
    # class (e.g. "yellow", "orange", "green", "red"), passed through
    # as-is rather than mapped to a fixed enum -- Kevin's own color
    # vocabulary is the source of truth, and a value this app hasn't seen
    # before (e.g. a red game some week) should still come through rather
    # than being dropped or misclassified.
    color: str
    # Kevin's free-text commentary for this game, verbatim.
    note: str


class WeatherSnapshot(BaseModel):
    season: int
    week: int
    scraped_at: str
    games: list[WeatherGame]
