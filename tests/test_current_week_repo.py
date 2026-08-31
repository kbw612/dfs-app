from pathlib import Path

from backend.repositories.current_week.current_week_repo import load_current_week, save_current_week
from backend.schemas.current_week.current_week import CurrentWeek


def test_load_returns_none_when_nothing_saved(tmp_path: Path):
    assert load_current_week(tmp_path) is None


def test_save_then_load_round_trips(tmp_path: Path):
    save_current_week(tmp_path, CurrentWeek(season=2025, week=9))
    assert load_current_week(tmp_path) == CurrentWeek(season=2025, week=9)


def test_save_overwrites_previous_value(tmp_path: Path):
    save_current_week(tmp_path, CurrentWeek(season=2025, week=9))
    save_current_week(tmp_path, CurrentWeek(season=2025, week=10))
    assert load_current_week(tmp_path) == CurrentWeek(season=2025, week=10)
