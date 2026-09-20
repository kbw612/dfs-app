from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.repositories.team_factors.team_factors_repo import (
    load_factor,
    load_factors_for_season,
    save_factor,
)
from backend.schemas.team_factors.team_factors import TeamFactorEntry


def test_factor_field_rejects_value_below_one():
    with pytest.raises(ValidationError):
        TeamFactorEntry(season=2025, team="CHI", position="WR", factor=0.5)


def test_factor_field_rejects_value_above_three():
    with pytest.raises(ValidationError):
        TeamFactorEntry(season=2025, team="CHI", position="WR", factor=3.5)


def test_factor_field_accepts_decimal_within_range():
    entry = TeamFactorEntry(season=2025, team="CHI", position="WR", factor=2.75)
    assert entry.factor == 2.75


def test_factor_defaults_to_none_when_unset():
    entry = TeamFactorEntry(season=2025, team="CHI", position="WR")
    assert entry.factor is None


def test_save_then_load_round_trips(tmp_path: Path):
    entry = TeamFactorEntry(season=2025, team="CHI", position="WR", factor=3.0)
    save_factor(tmp_path, entry)

    loaded = load_factor(tmp_path, 2025, "CHI", "WR")
    assert loaded == entry


def test_load_factor_returns_none_when_never_set(tmp_path: Path):
    assert load_factor(tmp_path, 2025, "CHI", "WR") is None


def test_save_factor_overwrites_previous_save(tmp_path: Path):
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="WR", factor=2.0))
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="WR", factor=3.0))

    assert load_factor(tmp_path, 2025, "CHI", "WR").factor == 3.0


def test_save_factor_does_not_touch_other_positions_on_same_team(tmp_path: Path):
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="WR", factor=3.0))
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="RB", factor=1.5))

    assert load_factor(tmp_path, 2025, "CHI", "WR").factor == 3.0
    assert load_factor(tmp_path, 2025, "CHI", "RB").factor == 1.5


def test_save_factor_does_not_touch_other_teams(tmp_path: Path):
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="WR", factor=3.0))
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="SF", position="WR", factor=1.0))

    assert load_factor(tmp_path, 2025, "CHI", "WR").factor == 3.0
    assert load_factor(tmp_path, 2025, "SF", "WR").factor == 1.0


def test_save_factor_does_not_touch_other_seasons(tmp_path: Path):
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="WR", factor=3.0))
    save_factor(tmp_path, TeamFactorEntry(season=2026, team="CHI", position="WR", factor=1.0))

    assert load_factor(tmp_path, 2025, "CHI", "WR").factor == 3.0
    assert load_factor(tmp_path, 2026, "CHI", "WR").factor == 1.0


def test_save_factor_with_none_clears_previously_saved_value(tmp_path: Path):
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="WR", factor=3.0))
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="WR", factor=None))

    assert load_factor(tmp_path, 2025, "CHI", "WR") is None


def test_load_factors_for_season_returns_every_saved_team_position_pair(tmp_path: Path):
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="WR", factor=3.0))
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="CHI", position="RB", factor=1.5))
    save_factor(tmp_path, TeamFactorEntry(season=2025, team="SF", position="QB", factor=2.5))
    save_factor(tmp_path, TeamFactorEntry(season=2026, team="CHI", position="WR", factor=1.0))

    season_2025 = load_factors_for_season(tmp_path, 2025)
    assert set(season_2025) == {("CHI", "WR"), ("CHI", "RB"), ("SF", "QB")}
    assert season_2025[("CHI", "WR")].factor == 3.0


def test_load_factors_for_season_empty_when_none_saved(tmp_path: Path):
    assert load_factors_for_season(tmp_path, 2025) == {}
