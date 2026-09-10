from pathlib import Path

from backend.repositories.salary_multiplier.salary_multiplier_repo import load_multipliers, save_multiplier


def test_load_multipliers_empty_when_never_saved(tmp_path: Path):
    assert load_multipliers(tmp_path) == {}


def test_save_then_load_round_trips(tmp_path: Path):
    save_multiplier(tmp_path, "DraftKings", 4.5)
    assert load_multipliers(tmp_path) == {"DraftKings": 4.5}


def test_save_multiplier_accumulates_multiple_platforms(tmp_path: Path):
    save_multiplier(tmp_path, "DraftKings", 4.5)
    save_multiplier(tmp_path, "FanDuel", 3.5)
    assert load_multipliers(tmp_path) == {"DraftKings": 4.5, "FanDuel": 3.5}


def test_save_multiplier_overwrites_same_platform(tmp_path: Path):
    save_multiplier(tmp_path, "DraftKings", 4.5)
    save_multiplier(tmp_path, "DraftKings", 5.0)
    assert load_multipliers(tmp_path) == {"DraftKings": 5.0}


def test_save_multiplier_none_clears_the_override(tmp_path: Path):
    save_multiplier(tmp_path, "DraftKings", 4.5)
    save_multiplier(tmp_path, "DraftKings", None)
    assert load_multipliers(tmp_path) == {}


def test_saved_file_lives_under_by_platform_json(tmp_path: Path):
    save_multiplier(tmp_path, "DraftKings", 4.5)
    assert (tmp_path / "by_platform.json").exists()
