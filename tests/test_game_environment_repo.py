from pathlib import Path

from backend.repositories.game_environment.game_environment_repo import (
    load_game_environment_for_week,
    save_game_environment,
)
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry


def make_entry(**overrides) -> GameEnvironmentEntry:
    fields = dict(
        season=2025,
        week=9,
        game_key="BUF-NO",
        home_team="BUF",
        away_team="NO",
        home_spread=-3.5,
        over_under=47.5,
        home_implied_total=27.0,
        away_implied_total=20.5,
    )
    fields.update(overrides)
    return GameEnvironmentEntry(**fields)


def test_save_then_load_round_trips(tmp_path: Path):
    entry = make_entry()
    save_game_environment(tmp_path, entry)

    loaded = load_game_environment_for_week(tmp_path, 2025, 9)
    assert loaded == {"BUF-NO": entry}


def test_load_returns_empty_when_nothing_saved(tmp_path: Path):
    assert load_game_environment_for_week(tmp_path, 2025, 9) == {}


def test_save_overwrites_same_game_same_week(tmp_path: Path):
    save_game_environment(tmp_path, make_entry(over_under=47.5))
    save_game_environment(tmp_path, make_entry(over_under=50.0))

    loaded = load_game_environment_for_week(tmp_path, 2025, 9)
    assert loaded["BUF-NO"].over_under == 50.0


def test_save_keeps_other_games_and_weeks_separate(tmp_path: Path):
    save_game_environment(tmp_path, make_entry(game_key="BUF-NO", week=9))
    save_game_environment(tmp_path, make_entry(game_key="KC-LAC", week=9, home_team="KC", away_team="LAC"))
    save_game_environment(tmp_path, make_entry(game_key="BUF-NO", week=10))

    week_9 = load_game_environment_for_week(tmp_path, 2025, 9)
    assert set(week_9) == {"BUF-NO", "KC-LAC"}

    week_10 = load_game_environment_for_week(tmp_path, 2025, 10)
    assert set(week_10) == {"BUF-NO"}
