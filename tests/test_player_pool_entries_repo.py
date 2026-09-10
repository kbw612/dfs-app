from pathlib import Path

from backend.repositories.player_pool.entries_repo import (
    load_entries_for_week,
    load_entry,
    save_entry,
)
from backend.schemas.player_pool.player_pool import PlayerPoolEntry


def test_load_entry_returns_none_when_not_saved(tmp_path: Path):
    assert load_entry(tmp_path, 2025, 9, "DraftKings", "Nobody") is None


def test_save_then_load_round_trips(tmp_path: Path):
    entry = PlayerPoolEntry(season=2025, week=9, platform="DraftKings", player="Gibbs", volume=3.0, talent=2.5)
    save_entry(tmp_path, entry)

    loaded = load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs")
    assert loaded == entry


def test_save_entry_overwrites_previous_save_for_same_week(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=2.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=3.0, talent=1.5))

    loaded = load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs")
    assert loaded.volume == 3.0
    assert loaded.talent == 1.5


def test_save_entry_does_not_touch_other_weeks(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=3.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=10, player="Gibbs", volume=1.0))

    assert load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs").volume == 3.0
    assert load_entry(tmp_path, 2025, 10, "DraftKings", "Gibbs").volume == 1.0


def test_save_entry_does_not_touch_other_platforms(tmp_path: Path):
    # Different platforms get their own file even for the same
    # (season, week, player) -- see _path's platform_file_prefix usage.
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, platform="DraftKings", player="Gibbs", volume=3.0))

    assert load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs").volume == 3.0


def test_load_entries_for_week_returns_every_saved_player(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=3.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Bijan Robinson", volume=2.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=10, player="Gibbs", volume=1.0))

    week_9 = load_entries_for_week(tmp_path, 2025, 9, "DraftKings")
    assert set(week_9) == {"Gibbs", "Bijan Robinson"}
    assert week_9["Gibbs"].volume == 3.0


def test_saved_file_lives_under_season_and_week_named_by_platform_prefix(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, platform="DraftKings", player="Gibbs", volume=3.0))
    assert (tmp_path / "2025" / "dk_player_factors_week9.json").exists()
