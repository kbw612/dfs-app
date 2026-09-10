from backend.services.salary_multiplier.engine import (
    default_multiplier,
    expected_fantasy_points,
    resolve_multiplier,
)


def test_default_multiplier_draftkings_is_four():
    assert default_multiplier("DraftKings") == 4.0


def test_default_multiplier_unknown_platform_falls_back_to_one():
    assert default_multiplier("FanDuel") == 1.0


def test_resolve_multiplier_uses_saved_value_when_present():
    assert resolve_multiplier("DraftKings", 5.0) == 5.0


def test_resolve_multiplier_falls_back_to_default_when_saved_is_none():
    assert resolve_multiplier("DraftKings", None) == 4.0


def test_resolve_multiplier_falls_back_to_fallback_default_for_unknown_platform():
    assert resolve_multiplier("FanDuel", None) == 1.0


def test_expected_fantasy_points_matches_user_examples():
    assert expected_fantasy_points(5000, 4.0) == 20.0
    assert expected_fantasy_points(9000, 4.0) == 36.0


def test_expected_fantasy_points_scales_with_multiplier():
    assert expected_fantasy_points(5000, 1.0) == 5.0
