from pathlib import Path

from backend.repositories.platform_settings.platform_settings_repo import (
    load_platform_settings,
    save_platform_settings,
)
from backend.schemas.platform_settings.platform_settings import PlatformSettings


def test_load_returns_none_when_nothing_saved(tmp_path: Path):
    assert load_platform_settings(tmp_path, 2025) is None


def test_save_then_load_round_trips(tmp_path: Path):
    entry = PlatformSettings(season=2025, platform="DraftKings", contest="Classic Main")
    save_platform_settings(tmp_path, entry)
    assert load_platform_settings(tmp_path, 2025) == entry


def test_save_overwrites_previous_value(tmp_path: Path):
    save_platform_settings(tmp_path, PlatformSettings(season=2025, platform="DraftKings", contest="Classic Main"))
    save_platform_settings(tmp_path, PlatformSettings(season=2025, platform="FanDuel", contest="Classic Main"))
    assert load_platform_settings(tmp_path, 2025) == PlatformSettings(
        season=2025, platform="FanDuel", contest="Classic Main"
    )


def test_save_does_not_touch_other_seasons(tmp_path: Path):
    save_platform_settings(tmp_path, PlatformSettings(season=2025, platform="DraftKings", contest="Classic Main"))
    save_platform_settings(tmp_path, PlatformSettings(season=2026, platform="FanDuel", contest="Classic Main"))

    assert load_platform_settings(tmp_path, 2025).platform == "DraftKings"
    assert load_platform_settings(tmp_path, 2026).platform == "FanDuel"
