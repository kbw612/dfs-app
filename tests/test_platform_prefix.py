import pytest

from backend.services.platform_settings.prefix import platform_file_prefix


def test_draftkings_maps_to_dk():
    assert platform_file_prefix("DraftKings") == "dk"


def test_unsupported_platform_raises_value_error():
    with pytest.raises(ValueError):
        platform_file_prefix("FanDuel")
