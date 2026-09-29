from pathlib import Path

from backend.repositories.star_players.star_players_repo import load_star_players, set_star_player


def test_load_returns_empty_when_nothing_saved(tmp_path: Path):
    result = load_star_players(tmp_path / "star_players.json")
    assert result.players == []


def test_set_star_player_adds_a_new_entry(tmp_path: Path):
    path = tmp_path / "star_players.json"
    result = set_star_player(path, "BAL", "Ronnie Stanley", True)
    assert [(e.team, e.player) for e in result.players] == [("BAL", "Ronnie Stanley")]

    loaded = load_star_players(path)
    assert [(e.team, e.player) for e in loaded.players] == [("BAL", "Ronnie Stanley")]


def test_set_star_player_false_removes_an_existing_entry(tmp_path: Path):
    path = tmp_path / "star_players.json"
    set_star_player(path, "BAL", "Ronnie Stanley", True)
    result = set_star_player(path, "BAL", "Ronnie Stanley", False)
    assert result.players == []


def test_set_star_player_false_on_never_starred_player_is_a_no_op(tmp_path: Path):
    path = tmp_path / "star_players.json"
    result = set_star_player(path, "BAL", "Nobody", False)
    assert result.players == []


def test_set_star_player_true_twice_is_idempotent(tmp_path: Path):
    path = tmp_path / "star_players.json"
    set_star_player(path, "BAL", "Ronnie Stanley", True)
    result = set_star_player(path, "BAL", "Ronnie Stanley", True)
    assert [(e.team, e.player) for e in result.players] == [("BAL", "Ronnie Stanley")]


def test_same_player_name_on_different_teams_does_not_collide(tmp_path: Path):
    path = tmp_path / "star_players.json"
    set_star_player(path, "BAL", "Mike Williams", True)
    result = set_star_player(path, "NYJ", "Mike Williams", True)
    assert {(e.team, e.player) for e in result.players} == {("BAL", "Mike Williams"), ("NYJ", "Mike Williams")}

    # Un-starring one team's entry leaves the other team's untouched.
    result = set_star_player(path, "BAL", "Mike Williams", False)
    assert [(e.team, e.player) for e in result.players] == [("NYJ", "Mike Williams")]


def test_multiple_teams_accumulate_and_stay_sorted(tmp_path: Path):
    path = tmp_path / "star_players.json"
    set_star_player(path, "NYJ", "Garrett Wilson", True)
    set_star_player(path, "BAL", "Ronnie Stanley", True)
    result = set_star_player(path, "BAL", "Lamar Jackson", True)
    assert [(e.team, e.player) for e in result.players] == [
        ("BAL", "Lamar Jackson"),
        ("BAL", "Ronnie Stanley"),
        ("NYJ", "Garrett Wilson"),
    ]
