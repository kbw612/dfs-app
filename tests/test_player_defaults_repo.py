from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.repositories.player_defaults.defaults_repo import (
    load_default,
    load_defaults_for_season,
    save_default,
)
from backend.schemas.player_defaults.player_defaults import PlayerDefaultEntry


def test_score_field_rejects_value_below_one():
    with pytest.raises(ValidationError):
        PlayerDefaultEntry(season=2025, player="Gibbs", volume=0.5)


def test_score_field_rejects_value_above_three():
    with pytest.raises(ValidationError):
        PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.5)


def test_score_field_accepts_decimal_within_range():
    entry = PlayerDefaultEntry(season=2025, player="Gibbs", volume=2.75)
    assert entry.volume == 2.75


def test_save_then_load_round_trips(tmp_path: Path):
    entry = PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0, talent=2.5)
    save_default(tmp_path, entry)

    loaded = load_default(tmp_path, 2025, "Gibbs")
    assert loaded == entry


def test_load_default_returns_none_when_never_set(tmp_path: Path):
    assert load_default(tmp_path, 2025, "Nobody") is None


def test_save_default_overwrites_previous_save(tmp_path: Path):
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Gibbs", volume=2.0))
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0, talent=1.5))

    loaded = load_default(tmp_path, 2025, "Gibbs")
    assert loaded.volume == 3.0
    assert loaded.talent == 1.5


def test_save_default_does_not_touch_other_players(tmp_path: Path):
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0))
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Bijan Robinson", volume=1.0))

    assert load_default(tmp_path, 2025, "Gibbs").volume == 3.0
    assert load_default(tmp_path, 2025, "Bijan Robinson").volume == 1.0


def test_save_default_does_not_touch_other_seasons(tmp_path: Path):
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0))
    save_default(tmp_path, PlayerDefaultEntry(season=2026, player="Gibbs", volume=1.0))

    assert load_default(tmp_path, 2025, "Gibbs").volume == 3.0
    assert load_default(tmp_path, 2026, "Gibbs").volume == 1.0


def test_load_defaults_for_season_returns_every_saved_player(tmp_path: Path):
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0))
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Bijan Robinson", volume=2.0))
    save_default(tmp_path, PlayerDefaultEntry(season=2026, player="Gibbs", volume=1.0))

    season_2025 = load_defaults_for_season(tmp_path, 2025)
    assert set(season_2025) == {"Gibbs", "Bijan Robinson"}
    assert season_2025["Gibbs"].volume == 3.0


def test_load_defaults_for_season_empty_when_none_saved(tmp_path: Path):
    assert load_defaults_for_season(tmp_path, 2025) == {}


def test_dfs_types_defaults_to_empty_list():
    entry = PlayerDefaultEntry(season=2025, player="Gibbs", volume=2.0)
    assert entry.dfs_types == []


def test_dfs_types_accepts_any_string_not_a_fixed_enum():
    # Deliberately not a Literal/enum -- see the schema module's docstring
    # on why new categories are added via the frontend checkbox list only.
    entry = PlayerDefaultEntry(season=2025, player="Gibbs", dfs_types=["Some Future Category"])
    assert entry.dfs_types == ["Some Future Category"]


def test_dfs_types_accepts_multiple_tags_at_once():
    entry = PlayerDefaultEntry(season=2025, player="Gibbs", dfs_types=["Boom/Bust", "Standalone"])
    assert entry.dfs_types == ["Boom/Bust", "Standalone"]


def test_dfs_types_round_trips_alongside_volume_and_talent(tmp_path: Path):
    entry = PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0, talent=2.5, dfs_types=["Boom/Bust"])
    save_default(tmp_path, entry)

    loaded = load_default(tmp_path, 2025, "Gibbs")
    assert loaded == entry
    assert loaded.dfs_types == ["Boom/Bust"]


def test_dfs_types_included_in_load_defaults_for_season(tmp_path: Path):
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Gibbs", dfs_types=["Boom/Bust"]))
    save_default(tmp_path, PlayerDefaultEntry(season=2025, player="Bijan Robinson"))

    season_2025 = load_defaults_for_season(tmp_path, 2025)
    assert season_2025["Gibbs"].dfs_types == ["Boom/Bust"]
    assert season_2025["Bijan Robinson"].dfs_types == []


def test_legacy_dfs_type_string_migrates_to_dfs_types_list(tmp_path: Path):
    # Pre-multi-tag files saved a single `dfs_type` string -- a file
    # written before this migration existed should still resolve to the
    # equivalent dfs_types list on load, not silently lose the tag.
    path = tmp_path / "2025" / "settings" / "player_factors.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"season": 2025, "defaults": {"Gibbs": {"volume": 2.0, "dfs_type": "Boom/Bust"}}}')

    loaded = load_default(tmp_path, 2025, "Gibbs")
    assert loaded.dfs_types == ["Boom/Bust"]
    assert loaded.volume == 2.0

    season_2025 = load_defaults_for_season(tmp_path, 2025)
    assert season_2025["Gibbs"].dfs_types == ["Boom/Bust"]


def test_legacy_dfs_type_null_migrates_to_empty_list(tmp_path: Path):
    path = tmp_path / "2025" / "settings" / "player_factors.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"season": 2025, "defaults": {"Gibbs": {"volume": 2.0, "dfs_type": null}}}')

    loaded = load_default(tmp_path, 2025, "Gibbs")
    assert loaded.dfs_types == []
