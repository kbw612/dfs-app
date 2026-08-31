from pathlib import Path

import pytest

from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv, save_salary_csv


def test_save_then_load_round_trips(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 3, "DraftKings", "Position,Name\nQB,Josh Allen\n")
    assert load_salary_csv(tmp_path, 2026, 3, "DraftKings") == "Position,Name\nQB,Josh Allen\n"


def test_load_returns_none_when_nothing_uploaded(tmp_path: Path):
    assert load_salary_csv(tmp_path, 2026, 3, "DraftKings") is None


def test_save_overwrites_previous_upload_for_same_week(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 3, "DraftKings", "old content")
    save_salary_csv(tmp_path, 2026, 3, "DraftKings", "new content")
    assert load_salary_csv(tmp_path, 2026, 3, "DraftKings") == "new content"


def test_file_lives_under_season_subfolder(tmp_path: Path):
    file_path = save_salary_csv(tmp_path, 2026, 3, "DraftKings", "content")
    assert file_path == tmp_path / "2026" / "dk_salary_week3.csv"


def test_different_seasons_do_not_collide_on_the_same_week(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 1, "DraftKings", "season 2026 week 1")
    save_salary_csv(tmp_path, 2027, 1, "DraftKings", "season 2027 week 1")

    assert load_salary_csv(tmp_path, 2026, 1, "DraftKings") == "season 2026 week 1"
    assert load_salary_csv(tmp_path, 2027, 1, "DraftKings") == "season 2027 week 1"


def test_different_weeks_do_not_collide_within_a_season(tmp_path: Path):
    save_salary_csv(tmp_path, 2026, 1, "DraftKings", "week 1")
    save_salary_csv(tmp_path, 2026, 2, "DraftKings", "week 2")

    assert load_salary_csv(tmp_path, 2026, 1, "DraftKings") == "week 1"
    assert load_salary_csv(tmp_path, 2026, 2, "DraftKings") == "week 2"


def test_unsupported_platform_raises_value_error(tmp_path: Path):
    with pytest.raises(ValueError):
        save_salary_csv(tmp_path, 2026, 3, "FanDuel", "content")
