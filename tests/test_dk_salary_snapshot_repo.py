from pathlib import Path

import pytest

from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv, save_salary_csv

CLASSIC_MAIN = "Classic Main"
ALL_GAMES = "All Games"


def test_save_then_load_round_trips(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "Position,Name\nQB,Josh Allen\n")
    assert load_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == "Position,Name\nQB,Josh Allen\n"


def test_load_returns_none_when_nothing_uploaded(tmp_path: Path):
    assert load_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) is None


def test_save_overwrites_previous_upload_for_same_week(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "old content")
    save_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "new content")
    assert load_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == "new content"


def test_file_lives_under_season_subfolder(tmp_path: Path):
    file_path = save_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "content")
    assert file_path == tmp_path / "2026" / "dk_salaries_classic_main_week3.csv"


def test_different_seasons_do_not_collide_on_the_same_week(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 1, "DraftKings", CLASSIC_MAIN, "season 2026 week 1")
    save_salary_csv(tmp_path, 2027, 1, "DraftKings", CLASSIC_MAIN, "season 2027 week 1")

    assert load_salary_csv(tmp_path, 2026, 1, "DraftKings", CLASSIC_MAIN) == "season 2026 week 1"
    assert load_salary_csv(tmp_path, 2027, 1, "DraftKings", CLASSIC_MAIN) == "season 2027 week 1"


def test_different_weeks_do_not_collide_within_a_season(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 1, "DraftKings", CLASSIC_MAIN, "week 1")
    save_salary_csv(tmp_path, 2026, 2, "DraftKings", CLASSIC_MAIN, "week 2")

    assert load_salary_csv(tmp_path, 2026, 1, "DraftKings", CLASSIC_MAIN) == "week 1"
    assert load_salary_csv(tmp_path, 2026, 2, "DraftKings", CLASSIC_MAIN) == "week 2"


def test_unsupported_platform_raises_value_error(tmp_path: Path):
    with pytest.raises(ValueError):
        save_salary_csv(tmp_path, 2026, 3, "FanDuel", CLASSIC_MAIN, "content")


def test_unsupported_contest_raises_value_error(tmp_path: Path):
    with pytest.raises(ValueError):
        save_salary_csv(tmp_path, 2026, 3, "DraftKings", "Some Other Contest", "content")


def test_all_games_uses_distinct_filename(tmp_path: Path):
    file_path = save_salary_csv(tmp_path, 2026, 3, "DraftKings", ALL_GAMES, "content")
    assert file_path == tmp_path / "2026" / "dk_salaries_classic_all_games_week3.csv"


def test_classic_main_and_all_games_do_not_collide(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "classic main content")
    save_salary_csv(tmp_path, 2026, 3, "DraftKings", ALL_GAMES, "all games content")

    assert load_salary_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == "classic main content"
    assert load_salary_csv(tmp_path, 2026, 3, "DraftKings", ALL_GAMES) == "all games content"
