import json
import threading
from pathlib import Path

from backend.repositories.player_pool.entries_repo import (
    _path,
    load_entries_for_week,
    load_entry,
    save_entry,
    save_ownership_scores,
)
from backend.schemas.player_pool.player_pool import PlayerPoolEntry


def test_load_entry_returns_none_when_not_saved(tmp_path: Path):
    assert load_entry(tmp_path, 2025, 9, "DraftKings", "Nobody") is None


def test_save_then_load_round_trips(tmp_path: Path):
    entry = PlayerPoolEntry(season=2025, week=9, platform="DraftKings", player="Gibbs", volume=3.0, talent=2.5)
    save_entry(tmp_path, entry)

    loaded = load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs")
    assert loaded == entry


def test_save_entry_overwrites_previous_save_for_same_week(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=2.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=3.0, talent=1.5))

    loaded = load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs")
    assert loaded.volume == 3.0
    assert loaded.talent == 1.5


def test_save_entry_does_not_touch_other_weeks(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=3.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=10, player="Gibbs", volume=1.0))

    assert load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs").volume == 3.0
    assert load_entry(tmp_path, 2025, 10, "DraftKings", "Gibbs").volume == 1.0


def test_save_entry_does_not_touch_other_platforms(tmp_path: Path):
    # Different platforms get their own file even for the same
    # (season, week, player) -- see _path's platform_file_prefix usage.
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, platform="DraftKings", player="Gibbs", volume=3.0))

    assert load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs").volume == 3.0


def test_load_entries_for_week_returns_every_saved_player(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=3.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Bijan Robinson", volume=2.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=10, player="Gibbs", volume=1.0))

    week_9 = load_entries_for_week(tmp_path, 2025, 9, "DraftKings")
    assert set(week_9) == {"Gibbs", "Bijan Robinson"}
    assert week_9["Gibbs"].volume == 3.0


def test_saved_file_lives_under_season_and_week_named_by_platform_prefix(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, platform="DraftKings", player="Gibbs", volume=3.0))
    assert (tmp_path / "2025" / "dk_player_factors_week9.json").exists()


def test_concurrent_saves_for_the_same_week_never_corrupt_the_file(tmp_path: Path):
    # Regression test for a real production incident: Game Matchup's
    # team+position propagation (see PlayerPoolView.tsx's
    # teammateKeysSharingMatchup) fires a save_entry() call for every
    # teammate on a team back to back, and a naive (unlocked, non-atomic)
    # read-modify-write let two of those threads interleave and left
    # data/nfl/2026/dk_player_factors_week1.json with one entry's closing
    # brace immediately followed by another write's un-opened tail --
    # every subsequent load raised json.JSONDecodeError("Extra data").
    # locked_read_modify_write (backend/repositories/atomic_json.py) is
    # what save_entry now goes through to prevent this.
    players = [f"Player {i}" for i in range(20)]

    def save(player: str) -> None:
        save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player=player, game_matchup=2.0))

    threads = [threading.Thread(target=save, args=(player,)) for player in players]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # The file must be valid, parseable JSON no matter how the 20 writes
    # interleaved -- a corrupted file (or one missing some of the 20
    # updates) both fail this.
    path = _path(tmp_path, 2025, 9, "DraftKings")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == set(players)

    week_9 = load_entries_for_week(tmp_path, 2025, 9, "DraftKings")
    assert set(week_9) == set(players)
    assert all(entry.game_matchup == 2.0 for entry in week_9.values())


def test_save_ownership_scores_creates_entries_for_unsaved_players(tmp_path: Path):
    save_ownership_scores(tmp_path, 2025, 9, "DraftKings", {"Gibbs": 3.0, "Chase": 1.0})

    week_9 = load_entries_for_week(tmp_path, 2025, 9, "DraftKings")
    assert week_9["Gibbs"].ownership == 3.0
    assert week_9["Chase"].ownership == 1.0


def test_save_ownership_scores_overwrites_only_ownership_field(tmp_path: Path):
    # A bulk Ownership refresh shouldn't clobber whatever Game Matchup/
    # Volume/Talent/Salary Value someone already saved this week for that
    # player -- only the `ownership` key should change.
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=3.0, game_matchup=2.5))

    save_ownership_scores(tmp_path, 2025, 9, "DraftKings", {"Gibbs": 1.0})

    loaded = load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs")
    assert loaded.ownership == 1.0
    assert loaded.volume == 3.0
    assert loaded.game_matchup == 2.5


def test_save_ownership_scores_does_not_touch_players_not_in_the_scores_dict(tmp_path: Path):
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Gibbs", ownership=2.0))
    save_entry(tmp_path, PlayerPoolEntry(season=2025, week=9, player="Chase", ownership=2.0))

    save_ownership_scores(tmp_path, 2025, 9, "DraftKings", {"Gibbs": 3.0})

    assert load_entry(tmp_path, 2025, 9, "DraftKings", "Gibbs").ownership == 3.0
    # Chase wasn't in this refresh's scores dict (e.g. skipped -- no
    # ownership_pct to score off of) -- their prior save stays untouched.
    assert load_entry(tmp_path, 2025, 9, "DraftKings", "Chase").ownership == 2.0
