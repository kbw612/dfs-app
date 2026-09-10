from pathlib import Path

from backend.repositories.dk_players.dk_players_repo import (
    dk_players_csv_path,
    load_dk_players_csv,
    save_dk_players_csv,
)


def test_filename_is_dk_players_not_doubled_prefix(tmp_path: Path):
    # Regression test -- this used to build "dk_dk_players.csv" (the
    # platform prefix "dk" plus a literal "_dk_players.csv" suffix).
    file_path = save_dk_players_csv(tmp_path, 2026, "DraftKings", "content")
    assert file_path == tmp_path / "2026" / "dk_players.csv"


def test_path_is_deterministic_whether_or_not_file_exists(tmp_path: Path):
    assert dk_players_csv_path(tmp_path, 2026, "DraftKings") == tmp_path / "2026" / "dk_players.csv"


def test_save_then_load_round_trips(tmp_path: Path):
    save_dk_players_csv(tmp_path, 2026, "DraftKings", "Name,Position\nJosh Allen,QB\n")
    assert load_dk_players_csv(tmp_path, 2026, "DraftKings") == "Name,Position\nJosh Allen,QB\n"


def test_load_returns_none_when_nothing_saved_yet(tmp_path: Path):
    assert load_dk_players_csv(tmp_path, 2026, "DraftKings") is None
