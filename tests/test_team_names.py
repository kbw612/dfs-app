from backend.services.shared.team_names import resolve_team_nickname


def test_resolve_team_nickname_known_abbreviations():
    assert resolve_team_nickname("LAC") == "Chargers"
    assert resolve_team_nickname("DAL") == "Cowboys"
    assert resolve_team_nickname("KC") == "Chiefs"


def test_resolve_team_nickname_is_case_insensitive_and_trims_whitespace():
    assert resolve_team_nickname("lac") == "Chargers"
    assert resolve_team_nickname(" LAC ") == "Chargers"


def test_resolve_team_nickname_unknown_abbrev_returns_none():
    assert resolve_team_nickname("ZZZ") is None


def test_resolve_team_nickname_covers_all_32_teams():
    from backend.services.shared.team_names import TEAM_NICKNAME_BY_ABBREV

    assert len(TEAM_NICKNAME_BY_ABBREV) == 32
    assert len(set(TEAM_NICKNAME_BY_ABBREV.values())) == 32  # no duplicate nicknames
