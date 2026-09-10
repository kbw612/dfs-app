from pathlib import Path

from backend.repositories.my_player_pool.my_player_pool_repo import load_membership, save_membership

CLASSIC_MAIN = "Classic Main"
ALL_GAMES = "All Games"


def test_load_membership_empty_when_never_saved(tmp_path: Path):
    assert load_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN) == {}


def test_save_then_load_round_trips(tmp_path: Path):
    save_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN, "Josh Allen", True)
    assert load_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": True}


def test_save_membership_accumulates_multiple_players(tmp_path: Path):
    save_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN, "Josh Allen", True)
    save_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN, "CeeDee Lamb", True)
    assert load_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": True, "CeeDee Lamb": True}


def test_save_membership_can_remove_a_player(tmp_path: Path):
    save_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN, "Josh Allen", True)
    save_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN, "Josh Allen", False)
    assert load_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": False}


def test_save_membership_does_not_touch_other_weeks(tmp_path: Path):
    save_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN, "Josh Allen", True)
    save_membership(tmp_path, 2025, 10, "DraftKings", CLASSIC_MAIN, "Josh Allen", False)

    assert load_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": True}
    assert load_membership(tmp_path, 2025, 10, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": False}


def test_different_contests_do_not_collide(tmp_path: Path):
    save_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN, "Josh Allen", True)
    save_membership(tmp_path, 2025, 9, "DraftKings", ALL_GAMES, "Josh Allen", False)

    assert load_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN) == {"Josh Allen": True}
    assert load_membership(tmp_path, 2025, 9, "DraftKings", ALL_GAMES) == {"Josh Allen": False}


def test_saved_file_lives_under_season_and_week_named_by_platform_prefix_and_contest_slug(tmp_path: Path):
    save_membership(tmp_path, 2025, 9, "DraftKings", CLASSIC_MAIN, "Josh Allen", True)
    assert (tmp_path / "2025" / "dk_my_player_pool_classic_main_week9.json").exists()
