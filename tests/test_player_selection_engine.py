from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.player_selection.engine import (
    default_selected,
    filter_selected_players,
    resolve_selected,
)


def _player(player: str, position: str, salary: int) -> OwnershipPlayer:
    return OwnershipPlayer(player=player, position=position, team="AAA", opponent="BBB", salary=salary)


def test_default_selected_excludes_cheap_qb():
    assert default_selected("QB", 4999) is False
    assert default_selected("QB", 5000) is True


def test_default_selected_excludes_cheap_rb():
    assert default_selected("RB", 4999) is False
    assert default_selected("RB", 5000) is True


def test_default_selected_excludes_cheap_wr():
    assert default_selected("WR", 3999) is False
    assert default_selected("WR", 4000) is True


def test_default_selected_excludes_cheap_te():
    assert default_selected("TE", 2999) is False
    assert default_selected("TE", 3000) is True


def test_default_selected_true_for_position_without_threshold():
    assert default_selected("DST", 1500) is True


def test_resolve_selected_uses_override_when_present():
    assert resolve_selected("Josh Allen", "QB", 8000, {"Josh Allen": False}) is False
    assert resolve_selected("Some Backup RB", "RB", 4000, {"Some Backup RB": True}) is True


def test_resolve_selected_falls_back_to_default_when_no_override():
    assert resolve_selected("Josh Allen", "QB", 8000, {}) is True
    assert resolve_selected("Cheap Guy", "RB", 4000, {}) is False


def test_filter_selected_players_drops_unselected_and_keeps_dst():
    players = [
        _player("Expensive QB", "QB", 8000),
        _player("Cheap QB", "QB", 4500),
        _player("Cheap DST", "DST", 2000),
    ]
    result = filter_selected_players(players, {})
    names = {p.player for p in result}
    assert names == {"Expensive QB", "Cheap DST"}


def test_filter_selected_players_respects_override_even_above_threshold():
    players = [_player("Expensive QB", "QB", 8000)]
    result = filter_selected_players(players, {"Expensive QB": False})
    assert result == []
