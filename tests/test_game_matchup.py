from backend.services.shared.game_matchup import game_key, game_label, resolve_away_home


def test_game_key_is_order_independent():
    assert game_key("LAR", "ARI") == game_key("ARI", "LAR")


def test_game_key_is_alphabetically_sorted():
    assert game_key("LAR", "ARI") == "ARI-LAR"


def test_game_label_puts_away_team_first():
    assert game_label("NO", "DET") == "NO @ DET"
    assert game_label("DET", "NO") == "DET @ NO"


def test_resolve_away_home_when_team_is_home():
    assert resolve_away_home("DET", "NO", True) == ("NO", "DET")


def test_resolve_away_home_when_team_is_away():
    assert resolve_away_home("NO", "DET", False) == ("NO", "DET")


def test_resolve_away_home_none_when_unknown():
    assert resolve_away_home("NO", "DET", None) is None
