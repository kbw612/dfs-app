from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.repositories.player_attributes.entries_repo import (
    load_entries_for_week,
    load_entry,
    resolve_carry_forward_value,
    save_entry,
)
from backend.schemas.player_attributes.player_attributes import PlayerAttributeEntry


def test_score_field_rejects_value_below_one():
    with pytest.raises(ValidationError):
        PlayerAttributeEntry(season=2025, week=9, player="Gibbs", volume=0.5)


def test_score_field_rejects_value_above_three():
    with pytest.raises(ValidationError):
        PlayerAttributeEntry(season=2025, week=9, player="Gibbs", volume=3.5)


def test_score_field_accepts_decimal_within_range():
    entry = PlayerAttributeEntry(season=2025, week=9, player="Gibbs", volume=2.75)
    assert entry.volume == 2.75


def test_save_then_load_round_trips(tmp_path: Path):
    entry = PlayerAttributeEntry(season=2025, week=9, player="Gibbs", volume=3.0, talent=2.5)
    save_entry(tmp_path, entry)

    loaded = load_entry(tmp_path, 2025, 9, "Gibbs")
    assert loaded == entry


def test_load_entry_returns_none_when_not_scored(tmp_path: Path):
    assert load_entry(tmp_path, 2025, 9, "Nobody") is None


def test_save_entry_overwrites_previous_save_for_same_week(tmp_path: Path):
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=9, player="Gibbs", volume=2.0))
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=9, player="Gibbs", volume=3.0, talent=1.5))

    loaded = load_entry(tmp_path, 2025, 9, "Gibbs")
    assert loaded.volume == 3.0
    assert loaded.talent == 1.5


def test_save_entry_does_not_touch_other_weeks(tmp_path: Path):
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=9, player="Gibbs", volume=3.0))
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=10, player="Gibbs", volume=1.0))

    assert load_entry(tmp_path, 2025, 9, "Gibbs").volume == 3.0
    assert load_entry(tmp_path, 2025, 10, "Gibbs").volume == 1.0


def test_load_entries_for_week_returns_every_saved_player(tmp_path: Path):
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=9, player="Gibbs", volume=3.0))
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=9, player="Bijan Robinson", volume=2.0))
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=10, player="Gibbs", volume=1.0))

    week_9 = load_entries_for_week(tmp_path, 2025, 9)
    assert set(week_9) == {"Gibbs", "Bijan Robinson"}
    assert week_9["Gibbs"].volume == 3.0


def test_resolve_carry_forward_value_finds_most_recent_earlier_week(tmp_path: Path):
    # Gibbs-style history: 3.0 through week 10, injured/unscored 11-13,
    # scored again as 2.0 in week 14 -- resolving week 16 should find the
    # week 14 value, not week 10's, even though week 14 is closer.
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=8, player="Gibbs", volume=3.0))
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=10, player="Gibbs", volume=3.0))
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=14, player="Gibbs", volume=2.0))

    assert resolve_carry_forward_value(tmp_path, 2025, 16, "Gibbs", "volume") == 2.0


def test_resolve_carry_forward_value_ignores_later_weeks(tmp_path: Path):
    save_entry(tmp_path, PlayerAttributeEntry(season=2025, week=12, player="Gibbs", volume=1.0))
    assert resolve_carry_forward_value(tmp_path, 2025, 10, "Gibbs", "volume") is None


def test_resolve_carry_forward_value_none_when_never_scored(tmp_path: Path):
    assert resolve_carry_forward_value(tmp_path, 2025, 10, "Nobody", "talent") is None


def test_resolve_carry_forward_value_rejects_unknown_field(tmp_path: Path):
    with pytest.raises(ValueError, match="Unknown Player Attribute field"):
        resolve_carry_forward_value(tmp_path, 2025, 10, "Gibbs", "not_a_field")
