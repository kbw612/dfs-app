import pytest

from backend.services.ownership.parsing import parse_ownership_pct


def test_parses_percent_string():
    assert parse_ownership_pct("30.5%") == 30.5


def test_none_input_returns_none():
    # Missing "% ownership" column entirely -- DK salaries are typically
    # available before ownership projections.
    assert parse_ownership_pct(None) is None


def test_blank_string_returns_none():
    # Column present, cell empty.
    assert parse_ownership_pct("") is None
    assert parse_ownership_pct("   ") is None


def test_malformed_value_still_raises():
    with pytest.raises(ValueError):
        parse_ownership_pct("abc%")
