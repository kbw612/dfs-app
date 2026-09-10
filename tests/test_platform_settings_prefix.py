import pytest

from backend.services.platform_settings.prefix import contest_slug, platform_file_prefix


def test_platform_file_prefix_known_platform():
    assert platform_file_prefix("DraftKings") == "dk"


def test_platform_file_prefix_unknown_platform_raises():
    with pytest.raises(ValueError):
        platform_file_prefix("FanDuel")


def test_contest_slug_classic_main():
    assert contest_slug("Classic Main") == "classic_main"


def test_contest_slug_all_games():
    assert contest_slug("All Games") == "all_games"


def test_contest_slug_unknown_contest_raises():
    with pytest.raises(ValueError):
        contest_slug("Showdown")
