"""
Turns a fresh scrape (backend/services/vegas_lines/scraper.py's
ScrapedGame list) into the VegasLinesSnapshot that gets saved -- the one
place the "initial never changes, current always does" rule
(backend/schemas/vegas_lines/vegas_lines.py's docstring) is implemented.

Per-game, not all-or-nothing: matched by game_key (falling back to the
raw away_name/home_name pair for games that don't resolve to a game_key
-- see scraper.py's docstring on why an unresolved game still comes back
rather than being dropped). A game seen for the first time this week
(no matching entry in the prior snapshot) gets its very own initial set
from this scrape, even if other games in the same snapshot already have
an older initial from earlier in the week -- there's no single
"snapshot-wide" first-scrape moment, just a first-scrape-per-game one.
"""

from __future__ import annotations

from backend.schemas.vegas_lines.vegas_lines import VegasLineGame, VegasLinesSnapshot, VegasLineValues
from backend.services.vegas_lines.scraper import ScrapedGame


def _match_key(game_key: str | None, away_name: str, home_name: str) -> tuple[str, str, str]:
    """A stable lookup key even for unresolved games (game_key is None)
    -- falls back to the raw scraped names, which is the best identity
    available for a game whose teams didn't resolve to an abbreviation."""
    return (game_key or "", away_name, home_name)


def merge_vegas_lines(
    existing: VegasLinesSnapshot | None,
    scraped_games: list[ScrapedGame],
    season: int,
    week: int,
    scraped_at: str,
) -> VegasLinesSnapshot:
    prior_by_key = {_match_key(g.game_key, g.away_name, g.home_name): g for g in (existing.games if existing else [])}

    games: list[VegasLineGame] = []
    for scraped in scraped_games:
        current = VegasLineValues(
            over_under=scraped.over_under,
            home_implied_total=scraped.home_implied_total,
            away_implied_total=scraped.away_implied_total,
        )
        prior = prior_by_key.get(_match_key(scraped.game_key, scraped.away_name, scraped.home_name))
        initial = prior.initial if prior is not None else current

        games.append(
            VegasLineGame(
                away_name=scraped.away_name,
                home_name=scraped.home_name,
                away_team=scraped.away_team,
                home_team=scraped.home_team,
                game_key=scraped.game_key,
                kickoff_label=scraped.kickoff_label,
                initial=initial,
                current=current,
            )
        )

    return VegasLinesSnapshot(
        season=season,
        week=week,
        initial_scraped_at=existing.initial_scraped_at if existing is not None else scraped_at,
        current_scraped_at=scraped_at,
        games=games,
    )
