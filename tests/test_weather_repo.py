from pathlib import Path

from backend.repositories.weather.weather_repo import load_weather, save_weather
from backend.schemas.weather.weather import WeatherGame, WeatherSnapshot


def make_snapshot(**overrides) -> WeatherSnapshot:
    fields = dict(
        season=2026,
        week=1,
        scraped_at="2026-09-08T10:00:00-04:00",
        games=[
            WeatherGame(
                away_name="New Orleans Saints",
                home_name="Baltimore Ravens",
                away_team="NO",
                home_team="BAL",
                game_key="BAL-NO",
                kickoff_label="1:00 PM ET",
                color="yellow",
                note="There's certainly rain around.",
            )
        ],
    )
    fields.update(overrides)
    return WeatherSnapshot(**fields)


def test_load_returns_none_when_nothing_saved(tmp_path: Path):
    assert load_weather(tmp_path, 2026, 1) is None


def test_save_then_load_round_trips(tmp_path: Path):
    snapshot = make_snapshot()
    save_weather(tmp_path, snapshot)

    loaded = load_weather(tmp_path, 2026, 1)
    assert loaded == snapshot


def test_save_overwrites_previous_save_for_same_week(tmp_path: Path):
    save_weather(tmp_path, make_snapshot(scraped_at="2026-09-08T10:00:00-04:00"))
    save_weather(tmp_path, make_snapshot(scraped_at="2026-09-10T15:00:00-04:00"))

    loaded = load_weather(tmp_path, 2026, 1)
    assert loaded.scraped_at == "2026-09-10T15:00:00-04:00"


def test_save_keeps_other_weeks_separate(tmp_path: Path):
    save_weather(tmp_path, make_snapshot(week=1))
    save_weather(tmp_path, make_snapshot(week=2))

    assert load_weather(tmp_path, 2026, 1).week == 1
    assert load_weather(tmp_path, 2026, 2).week == 2


def test_save_keeps_other_seasons_separate(tmp_path: Path):
    save_weather(tmp_path, make_snapshot(season=2025))
    save_weather(tmp_path, make_snapshot(season=2026))

    assert load_weather(tmp_path, 2025, 1).season == 2025
    assert load_weather(tmp_path, 2026, 1).season == 2026


def test_saved_file_lives_under_season_and_week_named_path(tmp_path: Path):
    save_weather(tmp_path, make_snapshot(season=2026, week=9))
    assert (tmp_path / "2026" / "weather_week9.json").exists()
