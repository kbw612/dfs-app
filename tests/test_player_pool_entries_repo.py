from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.repositories.player_pool.entries_repo import load_entries_for_week, load_entry, save_entry
from backend.schemas.player_pool.player_pool import PlayerPoolEntry


def test_score_field_rejects_value_below_one():
    with pytest.raises(ValidationError):
        PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=0.5)


def test_score_field_rejects_value_above_three():
    with pytest.raises(ValidationError):
        PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=3.5)


def test_score_field_accepts_decimal_within_range():
    entry = PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=2.75)
    assert entry.ownership == 2.75


def test_save_then_load_round_trips(tmp_path: Path):
    entry = PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=3.0, game_matchup=2.5)
    save_entry(tmp_path, entry)

    loaded = load_entry(tmp_path, 2025, 9, "Josh Allen")
    assert loaded == entry


def test_load_entry_returns_none_when_not_scored(tmp_path: Path):
    assert load_entry(tmp_path, 2025, 9, "Nobody") is None


def test_save_entry_overwrites_previous_save_for_same_week(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=2.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=3.0, game_matchup=1.5))

    loaded = load_entry(tmp_path, 2025, 9, "Josh Allen")
    assert loaded.ownership == 3.0
    assert loaded.game_matchup == 1.5


def test_save_entry_does_not_touch_other_weeks(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Josh Allen", game_matchup=3.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=10, player="Josh Allen", game_matchup=1.0))

    assert load_entry(tmp_path, 2025, 9, "Josh Allen").game_matchup == 3.0
    assert load_entry(tmp_path, 2025, 10, "Josh Allen").game_matchup == 1.0


def test_load_entries_for_week_returns_every_saved_player(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=3.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Lamar Jackson", ownership=2.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=10, player="Josh Allen", ownership=1.0))

    week_9 = load_entries_for_week(tmp_path, 2025, 9)
    assert set(week_9) == {"Josh Allen", "Lamar Jackson"}
    assert week_9["Josh Allen"].ownership == 3.0
