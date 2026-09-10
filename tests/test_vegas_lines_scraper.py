from pathlib import Path

from backend.services.vegas_lines.scraper import parse_games, resolve_team_abbrev

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "sample_vegas_lines_week.html").read_text()


def test_resolve_team_abbrev_known_nickname():
    assert resolve_team_abbrev("Hawks") == "SEA"
    assert resolve_team_abbrev("wft") == "WAS"


def test_resolve_team_abbrev_unknown_name():
    assert resolve_team_abbrev("Martians") is None


def test_parse_games_returns_every_game_including_unresolved():
    games, _ = parse_games(FIXTURE_HTML)
    # All 3 fixture games come back, even the one with an unresolvable
    # team name ("Martians") -- Vegas Lines is a browse view of the raw
    # scrape, not a direct write into scoring, so nothing gets dropped.
    assert len(games) == 3


def test_parse_games_resolves_team_names_and_game_key():
    games, _ = parse_games(FIXTURE_HTML)
    patriots_hawks = next(g for g in games if g.away_name == "Patriots")
    assert patriots_hawks.away_team == "NE"
    assert patriots_hawks.home_team == "SEA"
    assert patriots_hawks.game_key == "NE-SEA"


def test_parse_games_leaves_game_key_none_when_either_team_is_unresolved():
    games, _ = parse_games(FIXTURE_HTML)
    martians_game = next(g for g in games if g.away_name == "Martians")
    # "Martians" doesn't resolve; "Jaguars" does -- game_key still needs
    # both sides, so it stays None even though home_team resolved fine.
    assert martians_game.away_team is None
    assert martians_game.home_team == "JAX"
    assert martians_game.game_key is None


def test_parse_games_sets_implied_totals_and_over_under():
    games, _ = parse_games(FIXTURE_HTML)
    patriots_hawks = next(g for g in games if g.away_name == "Patriots")
    assert patriots_hawks.away_implied_total == 20.5
    assert patriots_hawks.home_implied_total == 24.0
    assert patriots_hawks.over_under == 44.5


def test_parse_games_sets_kickoff_label():
    # "Kickoff" prefix is stripped -- the label is just the date/time, since
    # the UI already labels this row as the kickoff.
    games, _ = parse_games(FIXTURE_HTML)
    patriots_hawks = next(g for g in games if g.away_name == "Patriots")
    assert patriots_hawks.kickoff_label == "Wednesday, Sep 9th 8:20pm Eastern"


def test_parse_games_reports_unresolved_team_name_as_a_message_not_a_skip():
    games, messages = parse_games(FIXTURE_HTML)
    assert len(games) == 3
    assert any("Martians" in m for m in messages)


def test_parse_games_empty_html_reports_no_games_found():
    games, messages = parse_games("<div>nothing here</div>")
    assert games == []
    assert any("No game blocks found" in m for m in messages)
