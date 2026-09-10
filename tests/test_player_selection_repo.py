from pathlib import Path

from backend.repositories.player_selection.player_selection_repo import load_overrides, save_override

CLASSIC_MAIN = "Classic Main"
ALL_GAMES = "All Games"


def test_load_returns_empty_dict_when_nothing_saved(tmp_path: Path):
    assert load_overrides(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == {}


def test_save_then_load_round_trips(tmp_path: Path):
    save_override(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "Josh Allen", False)
    assert load_overrides(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": False}


def test_save_accumulates_multiple_players(tmp_path: Path):
    save_override(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "Josh Allen", False)
    save_override(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "Some Backup RB", True)
    assert load_overrides(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == {
        "Josh Allen": False,
        "Some Backup RB": True,
    }


def test_save_overwrites_previous_value_for_same_player(tmp_path: Path):
    save_override(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "Josh Allen", False)
    save_override(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "Josh Allen", True)
    assert load_overrides(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": True}


def test_different_weeks_do_not_collide(tmp_path: Path):
    save_override(tmp_path, 2026, 1, "DraftKings", CLASSIC_MAIN, "Josh Allen", False)
    save_override(tmp_path, 2026, 2, "DraftKings", CLASSIC_MAIN, "Josh Allen", True)
    assert load_overrides(tmp_path, 2026, 1, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": False}
    assert load_overrides(tmp_path, 2026, 2, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": True}


def test_different_contests_do_not_collide(tmp_path: Path):
    save_override(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "Josh Allen", False)
    save_override(tmp_path, 2026, 3, "DraftKings", ALL_GAMES, "Josh Allen", True)
    assert load_overrides(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": False}
    assert load_overrides(tmp_path, 2026, 3, "DraftKings", ALL_GAMES) == {"Josh Allen": True}
