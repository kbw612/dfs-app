from pathlib import Path

from backend.services.depth_charts.scraper import extract_injury_status, parse_teams

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "sample_depth_chart.html").read_text()


def test_extract_injury_status_with_status():
    assert extract_injury_status("James Conner (Q)") == ("James Conner", "Q")


def test_extract_injury_status_without_status():
    assert extract_injury_status("Jacoby Brissett") == ("Jacoby Brissett", None)


def test_extract_injury_status_multi_word_name():
    assert extract_injury_status("Ka'ena De Cambra") == ("Ka'ena De Cambra", None)


def test_parse_teams_extracts_both_teams():
    teams, messages = parse_teams(FIXTURE_HTML)
    assert [t.team_name for t in teams] == ["Arizona Cardinals", "Atlanta Falcons"]
    # 2 teams in the fixture, not the real 32 -- parse_teams should warn about it.
    assert any(m.step == "scrape" and m.level == "warning" for m in messages)


def test_parse_teams_preserves_order_and_status():
    teams, _ = parse_teams(FIXTURE_HTML)
    cardinals = teams[0]
    assert [p.player for p in cardinals.positions["QB"]] == ["Jacoby Brissett", "Gardner Minshew"]
    assert cardinals.positions["RB"][1].status == "Q"
    assert cardinals.positions["RB"][0].status is None


def test_parse_teams_team_abbrev_and_defensive_formation_not_set_yet():
    teams, _ = parse_teams(FIXTURE_HTML)
    for team in teams:
        assert team.team_abbrev is None
        assert team.defensive_formation is None


def test_parse_teams_excludes_coaches():
    """The fixture's Arizona Cardinals block includes a Coaches section
    (matching footballguys.com's real page, per the original script's
    "Coachess" CSV column) -- it should never show up in `positions`."""
    teams, _ = parse_teams(FIXTURE_HTML)
    cardinals = teams[0]
    assert "Coaches" not in cardinals.positions
    assert "COACHES" not in cardinals.positions
    assert not any(key.upper() == "COACHES" for key in cardinals.positions)
