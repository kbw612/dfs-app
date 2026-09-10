"""
Vegas Lines: the raw per-game scrape of oneweekseason.com's public week
page (backend/services/vegas_lines/scraper.py) -- kickoff time, both
teams' names exactly as scraped, and each of two snapshots in time:

    initial  -- the very first scrape taken for this (season, week).
                Never overwritten again once set, so it's a fixed
                baseline no matter how many times you re-scrape later
                in the week.
    current  -- whatever the most recent scrape found. Overwritten every
                time you re-scrape.

This is deliberately a separate resource from GameEnvironmentEntry
(backend/schemas/game_environment/game_environment.py) rather than
writing scraped values straight into it -- Vegas Lines is a raw,
browsable record of "what oneweekseason.com said, and how it's moved
since the start of the week," independent of whether/when anyone applies
it to this week's actual scoring inputs. Applying `current`'s values into
GameEnvironmentEntry (see backend/api/vegas_lines/apply.py) is a distinct,
explicit action -- scraping alone never touches scoring.

away_team/home_team/game_key are None when the scraped name didn't match
any entry in scraper.py's team-alias table -- the game still shows up
here (this is a browse view of the raw scrape, unresolved names and all),
it just can't be matched to a game_key or applied to Game Environment
until/unless the alias table is extended to cover it.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class VegasLineValues(BaseModel):
    over_under: Optional[float] = None
    home_implied_total: Optional[float] = None
    away_implied_total: Optional[float] = None


class VegasLineGame(BaseModel):
    # Exactly as scraped, e.g. "Patriots" / "Hawks" -- for display. Not
    # necessarily this app's team abbreviation (see away_team/home_team).
    away_name: str
    home_name: str
    # This app's abbreviation, resolved via scraper.py's alias table --
    # None if away_name/home_name didn't match anything in it.
    away_team: Optional[str] = None
    home_team: Optional[str] = None
    # Alphabetically-sorted "TEAM1-TEAM2", same convention as everywhere
    # else a game is keyed in this app -- None whenever either team
    # didn't resolve (nothing stable to key on yet).
    game_key: Optional[str] = None
    # Verbatim scraped kickoff line, e.g. "Kickoff Wednesday, Sep 9th
    # 8:20pm Eastern" -- display only, never parsed into a real datetime.
    kickoff_label: Optional[str] = None
    initial: VegasLineValues
    current: VegasLineValues


class VegasLinesSnapshot(BaseModel):
    season: int
    week: int
    # ISO timestamps -- when `initial` was captured (the first-ever scrape
    # for this season/week) and when `current` was last refreshed (every
    # scrape after that, including the very first one, where the two are
    # equal).
    initial_scraped_at: str
    current_scraped_at: str
    games: list[VegasLineGame]
