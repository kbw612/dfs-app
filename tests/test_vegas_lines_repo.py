from pathlib import Path

from backend.repositories.vegas_lines.vegas_lines_repo import load_vegas_lines, save_vegas_lines
from backend.schemas.vegas_lines.vegas_lines import VegasLineGame, VegasLinesSnapshot, VegasLineValues


def make_snapshot(**overrides) -> VegasLinesSnapshot:
    fields = dict(
        season=2026,
        week=1,
        initial_scraped_at="2026-09-08T10:00:00-04:00",
        current_scraped_at="2026-09-08T10:00:00-04:00",
        games=[
            VegasLineGame(
                away_name="Patriots",
                home_name="Hawks",
                away_team="NE",
                home_team="SEA",
                game_key="NE-SEA",
                kickoff_label="Kickoff Wednesday, Sep 9th 8:20pm Eastern",
                initial=VegasLineValues(over_under=44.5, home_implied_total=24.0, away_implied_total=20.5),
                current=VegasLineValues(over_under=44.5, home_implied_total=24.0, away_implied_total=20.5),
            )
        ],
    )
    fields.update(overrides)
    return VegasLinesSnapshot(**fields)


def test_load_returns_none_when_nothing_saved(tmp_path: Path):
    assert load_vegas_lines(tmp_path, 2026, 1) is None


def test_save_then_load_round_trips(tmp_path: Path):
    snapshot = make_snapshot()
    save_vegas_lines(tmp_path, snapshot)

    loaded = load_vegas_lines(tmp_path, 2026, 1)
    assert loaded == snapshot


def test_save_overwrites_previous_save_for_same_week(tmp_path: Path):
    save_vegas_lines(tmp_path, make_snapshot(current_scraped_at="2026-09-08T10:00:00-04:00"))
    save_vegas_lines(tmp_path, make_snapshot(current_scraped_at="2026-09-10T15:00:00-04:00"))

    loaded = load_vegas_lines(tmp_path, 2026, 1)
    assert loaded.current_scraped_at == "2026-09-10T15:00:00-04:00"


def test_save_keeps_other_weeks_separate(tmp_path: Path):
    save_vegas_lines(tmp_path, make_snapshot(week=1))
    save_vegas_lines(tmp_path, make_snapshot(week=2))

    assert load_vegas_lines(tmp_path, 2026, 1).week == 1
    assert load_vegas_lines(tmp_path, 2026, 2).week == 2


def test_save_keeps_other_seasons_separate(tmp_path: Path):
    save_vegas_lines(tmp_path, make_snapshot(season=2025))
    save_vegas_lines(tmp_path, make_snapshot(season=2026))

    assert load_vegas_lines(tmp_path, 2025, 1).season == 2025
    assert load_vegas_lines(tmp_path, 2026, 1).season == 2026


def test_saved_file_lives_under_season_and_week_named_path(tmp_path: Path):
    save_vegas_lines(tmp_path, make_snapshot(season=2026, week=9))
    assert (tmp_path / "2026" / "vegas_lines_week9.json").exists()
