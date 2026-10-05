from backend.repositories.game_recap.game_recap_repo import load_game_recaps, save_game_recaps
from backend.schemas.game_recap.game_recap import GameRecapEntry, GameRecapWeekSnapshot, find_team_recap


def _snapshot(season=2026, week=3) -> GameRecapWeekSnapshot:
    return GameRecapWeekSnapshot(
        season=season,
        week=week,
        scraped_at="2026-09-30T12:00:00-05:00",
        source_url="https://walterfootball.com/nflreview2026_03.php",
        games=[
            GameRecapEntry(
                away_team="ATL", home_team="GB", away_team_score=35, home_team_score=14, recap_text="Falcons won."
            ),
            GameRecapEntry(
                away_team="SEA", home_team="WAS", away_team_score=31, home_team_score=33, recap_text="Close one."
            ),
        ],
    )


def test_round_trip_save_and_load(tmp_path):
    save_game_recaps(tmp_path, _snapshot())
    loaded = load_game_recaps(tmp_path, 2026, 3)
    assert loaded is not None
    assert loaded.season == 2026
    assert loaded.week == 3
    assert len(loaded.games) == 2
    assert loaded.games[0].recap_text == "Falcons won."


def test_load_returns_none_when_no_file(tmp_path):
    assert load_game_recaps(tmp_path, 2026, 99) is None


def test_save_overwrites_existing_file(tmp_path):
    save_game_recaps(tmp_path, _snapshot())
    updated = _snapshot()
    updated.games = updated.games[:1]
    save_game_recaps(tmp_path, updated)
    loaded = load_game_recaps(tmp_path, 2026, 3)
    assert len(loaded.games) == 1


def test_find_team_recap_matches_either_side():
    snapshot = _snapshot()
    assert find_team_recap(snapshot, "GB") is not None
    assert find_team_recap(snapshot, "WAS") is not None
    assert find_team_recap(snapshot, "WAS").recap_text == "Close one."


def test_find_team_recap_none_when_team_not_in_any_game():
    snapshot = _snapshot()
    assert find_team_recap(snapshot, "KC") is None


def test_find_team_recap_none_when_snapshot_missing():
    assert find_team_recap(None, "GB") is None
