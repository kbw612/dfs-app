from pathlib import Path

from backend.services.weather.scraper import parse_notes, resolve_team_abbrev

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "sample_weather_week.html").read_text()

# A small stand-in for config/team-info.csv's Full-Name -> abbrev map, so
# these tests don't depend on the real file's exact contents.
_ABBREV_BY_FULL_NAME = {
    "New Orleans Saints": "NO",
    "Baltimore Ravens": "BAL",
    "Chicago Bears": "CHI",
    "Green Bay Packers": "GB",
    "Jacksonville Jaguars": "JAX",
}


def test_resolve_team_abbrev_known_name():
    assert resolve_team_abbrev("Baltimore Ravens", _ABBREV_BY_FULL_NAME) == "BAL"


def test_resolve_team_abbrev_unknown_name():
    assert resolve_team_abbrev("Martians", _ABBREV_BY_FULL_NAME) is None


def test_parse_notes_returns_every_card_including_unresolved():
    notes, _ = parse_notes(FIXTURE_HTML, _ABBREV_BY_FULL_NAME)
    # All 3 fixture cards come back, even the one with an unresolvable team
    # name ("Martians") -- same "browse view of the raw scrape, nothing
    # dropped" behavior as Vegas Lines.
    assert len(notes) == 3


def test_parse_notes_resolves_team_names_and_game_key():
    notes, _ = parse_notes(FIXTURE_HTML, _ABBREV_BY_FULL_NAME)
    saints_ravens = next(n for n in notes if n.away_name == "New Orleans Saints")
    assert saints_ravens.away_team == "NO"
    assert saints_ravens.home_team == "BAL"
    assert saints_ravens.game_key == "BAL-NO"


def test_parse_notes_leaves_game_key_none_when_either_team_is_unresolved():
    notes, _ = parse_notes(FIXTURE_HTML, _ABBREV_BY_FULL_NAME)
    martians_game = next(n for n in notes if n.away_name == "Martians")
    assert martians_game.away_team is None
    assert martians_game.home_team == "JAX"
    assert martians_game.game_key is None


def test_parse_notes_sets_color_from_class_suffix():
    notes, _ = parse_notes(FIXTURE_HTML, _ABBREV_BY_FULL_NAME)
    assert next(n for n in notes if n.away_name == "New Orleans Saints").color == "yellow"
    assert next(n for n in notes if n.away_name == "Chicago Bears").color == "orange"
    assert next(n for n in notes if n.away_name == "Martians").color == "green"


def test_parse_notes_sets_kickoff_label_and_note_text():
    notes, _ = parse_notes(FIXTURE_HTML, _ABBREV_BY_FULL_NAME)
    saints_ravens = next(n for n in notes if n.away_name == "New Orleans Saints")
    assert saints_ravens.kickoff_label == "1:00 PM ET"
    assert saints_ravens.note.startswith("There's certainly rain around")


def test_parse_notes_reports_unresolved_team_name_as_a_message_not_a_skip():
    notes, messages = parse_notes(FIXTURE_HTML, _ABBREV_BY_FULL_NAME)
    assert len(notes) == 3
    assert any("Martians" in m for m in messages)


def test_parse_notes_empty_html_reports_no_cards_found():
    notes, messages = parse_notes("<div>nothing here</div>", _ABBREV_BY_FULL_NAME)
    assert notes == []
    assert any("No weather note cards found" in m for m in messages)
