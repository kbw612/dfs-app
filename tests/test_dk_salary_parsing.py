import pytest

from backend.services.dk_salary.dk_salary_parsing import parse_game_info


def test_home_team_gets_away_team_as_opponent():
    opponent, is_home = parse_game_info("NO@DET 09/13/2026 01:00PM ET", "DET")
    assert opponent == "NO"
    assert is_home is True


def test_away_team_gets_home_team_as_opponent():
    opponent, is_home = parse_game_info("NO@DET 09/13/2026 01:00PM ET", "NO")
    assert opponent == "DET"
    assert is_home is False


def test_ignores_date_time_suffix():
    # Only the "AWAY@HOME" prefix before the first space matters.
    opponent, _ = parse_game_info("BUF@HOU 09/13/2026 01:00PM ET", "BUF")
    assert opponent == "HOU"


def test_normalizes_la_team_abbreviations():
    opponent, is_home = parse_game_info("ARI@LA 09/13/2026 04:25PM ET", "LA")
    assert opponent == "ARI"
    assert is_home is True


def test_raises_when_team_not_in_matchup():
    with pytest.raises(ValueError, match="isn't playing"):
        parse_game_info("NO@DET 09/13/2026 01:00PM ET", "KC")


def test_raises_when_no_at_sign():
    with pytest.raises(ValueError, match="Can't parse"):
        parse_game_info("TBD", "DET")
