"""
Game Recaps: the raw per-game recap text scraped from walterfootball.com's
public "NFL Game Recaps" page (backend/services/game_recap/
game_recap_scraper.py) for a given (season, week) -- the site's own
written summary of what happened in each game, stored and shown VERBATIM
(this app never summarizes or rewrites it) alongside the final score each
team put up.

away_team/home_team ARE the real home/away split (unlike an earlier
version of this schema, which kept team_a/team_b in whatever order the
site's own score line happened to list them) -- the site's score-line text
itself isn't a reliable source for this (it wrote "Redskins 33, Seahawks
31" for a game SEA actually played AT Washington, home team listed first
that time), so the scraper resolves the real order from the uploaded
Schedule file instead, via the same opponent_and_location lookup the Game
Logs tabs already use for their own "vs"/"@" display (see
backend/services/schedule/schedule_loader.py). When the Schedule file
doesn't cover a game (not uploaded, or either team's own name didn't
resolve to this app's abbreviation), the scraper falls back to the order
it actually scraped and flags that game in /scrape's own `messages` -- it's
still shown as away_team/home_team, just not a confirmed assignment.

team_a/team_b are this app's own abbreviations (config/team-info.csv) when
the scraped name resolved via game_recap_scraper.py's alias table, else the
raw scraped name verbatim (e.g. an unrecognized or future site spelling) --
same "show it anyway, just unresolved" convention as VegasLineGame's own
away_team/home_team (backend/schemas/vegas_lines/vegas_lines.py), so one
odd team name doesn't drop an entire game's recap from the saved snapshot.
"""

from __future__ import annotations

from pydantic import BaseModel


class GameRecapEntry(BaseModel):
    # This app's abbreviation when resolved, else the raw scraped name --
    # see this module's own docstring for the fallback when the Schedule
    # file can't confirm which side is actually home/away.
    away_team: str
    home_team: str
    away_team_score: int
    home_team_score: int
    # The site's own recap paragraphs, verbatim, joined with blank lines
    # between paragraphs -- never summarized or reworded by this app (see
    # this module's own docstring).
    recap_text: str


class GameRecapWeekSnapshot(BaseModel):
    season: int
    week: int
    # ISO timestamp of the scrape that produced this file -- overwritten
    # every time this (season, week) is re-scraped (no initial/current
    # split like Vegas Lines; a recap doesn't move during the week the way
    # a betting line does, so there's nothing worth keeping a baseline of).
    scraped_at: str
    # The exact page this came from, for the frontend's own "Source:" link
    # back to walterfootball.com next to the displayed recap text.
    source_url: str
    games: list[GameRecapEntry]


def find_team_recap(snapshot: GameRecapWeekSnapshot | None, team: str) -> GameRecapEntry | None:
    """The one game in `snapshot` involving `team` (as either away_team or
    home_team), or None if `snapshot` is None (nothing scraped for this
    season/week yet) or no game in it mentions `team` (team on a bye, or an
    unresolved/misspelled name that never matched this abbreviation)."""
    if snapshot is None:
        return None
    for game in snapshot.games:
        if game.away_team == team or game.home_team == team:
            return game
    return None
