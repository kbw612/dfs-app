from pathlib import Path

from backend.repositories.name_aliases.name_aliases_repo import load_name_aliases, save_name_aliases
from backend.schemas.name_aliases.name_aliases import NameAlias


def test_load_name_aliases_missing_file_returns_empty_list(tmp_path: Path):
    assert load_name_aliases(tmp_path / "does-not-exist.json") == []


def test_save_and_load_name_aliases_round_trip(tmp_path: Path):
    path = tmp_path / "name-aliases.json"
    aliases = [NameAlias(alias="James Cook III", canonical="James Cook"), NameAlias(alias="Gabe Davis", canonical="Gabriel Davis")]
    save_name_aliases(path, aliases)
    assert load_name_aliases(path) == aliases


def test_save_name_aliases_fully_replaces_previous_list(tmp_path: Path):
    path = tmp_path / "name-aliases.json"
    save_name_aliases(path, [NameAlias(alias="A", canonical="B")])
    save_name_aliases(path, [NameAlias(alias="C", canonical="D")])
    assert load_name_aliases(path) == [NameAlias(alias="C", canonical="D")]
