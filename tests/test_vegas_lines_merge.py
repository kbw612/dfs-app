from backend.services.vegas_lines.merge import merge_vegas_lines
from backend.services.vegas_lines.scraper import ScrapedGame


def make_scraped(**overrides) -> ScrapedGame:
    fields = dict(
        away_name="Patriots",
        home_name="Hawks",
        away_team="NE",
        home_team="SEA",
        game_key="NE-SEA",
        kickoff_label="Kickoff Wednesday, Sep 9th 8:20pm Eastern",
        over_under=44.5,
        home_implied_total=24.0,
        away_implied_total=20.5,
    )
    fields.update(overrides)
    return ScrapedGame(**fields)


def test_first_scrape_sets_initial_and_current_equal():
    snapshot = merge_vegas_lines(None, [make_scraped()], 2026, 1, "2026-09-08T10:00:00-04:00")

    game = snapshot.games[0]
    assert game.initial == game.current
    assert snapshot.initial_scraped_at == "2026-09-08T10:00:00-04:00"
    assert snapshot.current_scraped_at == "2026-09-08T10:00:00-04:00"


def test_second_scrape_updates_current_but_not_initial():
    first = merge_vegas_lines(None, [make_scraped(over_under=44.5)], 2026, 1, "2026-09-08T10:00:00-04:00")

    second = merge_vegas_lines(
        first, [make_scraped(over_under=46.0, home_implied_total=25.5)], 2026, 1, "2026-09-10T15:00:00-04:00"
    )

    game = second.games[0]
    assert game.initial.over_under == 44.5
    assert game.current.over_under == 46.0
    assert game.current.home_implied_total == 25.5
    assert second.initial_scraped_at == "2026-09-08T10:00:00-04:00"
    assert second.current_scraped_at == "2026-09-10T15:00:00-04:00"


def test_new_game_appearing_mid_week_gets_its_own_fresh_initial():
    first = merge_vegas_lines(None, [make_scraped()], 2026, 1, "2026-09-08T10:00:00-04:00")

    second_game = make_scraped(
        away_name="Browns", home_name="Jaguars", away_team="CLE", home_team="JAX", game_key="CLE-JAX", over_under=40.5
    )
    second = merge_vegas_lines(first, [make_scraped(), second_game], 2026, 1, "2026-09-10T15:00:00-04:00")

    new_game = next(g for g in second.games if g.game_key == "CLE-JAX")
    assert new_game.initial == new_game.current
    assert new_game.initial.over_under == 40.5


def test_unresolved_games_match_by_raw_names_not_game_key():
    unresolved = make_scraped(
        away_name="Martians", home_name="Jaguars", away_team=None, home_team=None, game_key=None, over_under=40.5
    )
    first = merge_vegas_lines(None, [unresolved], 2026, 1, "2026-09-08T10:00:00-04:00")

    updated_unresolved = make_scraped(
        away_name="Martians", home_name="Jaguars", away_team=None, home_team=None, game_key=None, over_under=41.0
    )
    second = merge_vegas_lines(first, [updated_unresolved], 2026, 1, "2026-09-10T15:00:00-04:00")

    game = second.games[0]
    assert game.initial.over_under == 40.5
    assert game.current.over_under == 41.0


def test_games_no_longer_in_the_new_scrape_are_dropped():
    first = merge_vegas_lines(None, [make_scraped()], 2026, 1, "2026-09-08T10:00:00-04:00")

    second = merge_vegas_lines(first, [], 2026, 1, "2026-09-10T15:00:00-04:00")

    assert second.games == []
