from pathlib import Path

import pytest

from backend.repositories.ownership.projections_repo import load_projections_csv, save_projections_csv


def test_save_then_load_round_trips(tmp_path: Path):
    save_projections_csv(tmp_path, 2026, 3, "DraftKings", "Player,Position\nJosh Allen,QB\n")
    assert load_projections_csv(tmp_path, 2026, 3, "DraftKings") == "Player,Position\nJosh Allen,QB\n"


def test_load_returns_none_when_nothing_uploaded(tmp_path: Path):
    assert load_projections_csv(tmp_path, 2026, 3, "DraftKings") is None


def test_save_overwrites_previous_upload_for_same_week(tmp_path: Path):
    save_projections_csv(tmp_path, 2026, 3, "DraftKings", "old content")
    save_projections_csv(tmp_path, 2026, 3, "DraftKings", "new content")
    assert load_projections_csv(tmp_path, 2026, 3, "DraftKings") == "new content"


def test_file_lives_under_season_subfolder(tmp_path: Path):
    file_path = save_projections_csv(tmp_path, 2026, 3, "DraftKings", "content")
    assert file_path == tmp_path / "2026" / "dk_ownership_projections_week3.csv"


def test_different_weeks_do_not_collide_within_a_season(tmp_path: Path):
    save_projections_csv(tmp_path, 2026, 1, "DraftKings", "week 1")
    save_projections_csv(tmp_path, 2026, 2, "DraftKings", "week 2")

    assert load_projections_csv(tmp_path, 2026, 1, "DraftKings") == "week 1"
    assert load_projections_csv(tmp_path, 2026, 2, "DraftKings") == "week 2"


def test_unsupported_platform_raises_value_error(tmp_path: Path):
    with pytest.raises(ValueError):
        save_projections_csv(tmp_path, 2026, 3, "FanDuel", "content")
