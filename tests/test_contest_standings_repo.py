from pathlib import Path

import pytest

from backend.repositories.contest_results.contest_standings_repo import (
    contest_standings_csv_path,
    load_contest_standings_csv,
    save_contest_standings_csv,
)

CLASSIC_MAIN = "Classic Main"
ALL_GAMES = "All Games"


def test_save_then_load_round_trips(tmp_path: Path):
    save_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "Rank,Entry\n1,me\n")
    assert load_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == "Rank,Entry\n1,me\n"


def test_load_returns_none_when_nothing_uploaded(tmp_path: Path):
    assert load_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) is None


def test_save_overwrites_previous_upload_for_same_week(tmp_path: Path):
    save_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "old content")
    save_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "new content")
    assert load_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == "new content"


def test_classic_main_file_lives_under_season_subfolder(tmp_path: Path):
    file_path = save_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "content")
    assert file_path == tmp_path / "2026" / "dk_contest_standings_classic_main_week3.csv"


def test_all_games_uses_distinct_filename(tmp_path: Path):
    file_path = save_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", ALL_GAMES, "content")
    assert file_path == tmp_path / "2026" / "dk_contest_standings_classic_all_games_week3.csv"


def test_classic_main_and_all_games_do_not_collide(tmp_path: Path):
    save_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN, "classic main content")
    save_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", ALL_GAMES, "all games content")

    assert load_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == "classic main content"
    assert load_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", ALL_GAMES) == "all games content"


def test_path_is_deterministic_whether_or_not_file_exists(tmp_path: Path):
    expected = tmp_path / "2026" / "dk_contest_standings_classic_main_week3.csv"
    assert contest_standings_csv_path(tmp_path, 2026, 3, "DraftKings", CLASSIC_MAIN) == expected


def test_unsupported_platform_raises_value_error(tmp_path: Path):
    with pytest.raises(ValueError):
        save_contest_standings_csv(tmp_path, 2026, 3, "FanDuel", CLASSIC_MAIN, "content")


def test_unsupported_contest_raises_value_error(tmp_path: Path):
    with pytest.raises(ValueError):
        save_contest_standings_csv(tmp_path, 2026, 3, "DraftKings", "Some Other Contest", "content")
