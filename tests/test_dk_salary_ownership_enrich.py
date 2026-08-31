from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct


def make_player(player, ownership_pct=None):
    return OwnershipPlayer(
        player=player, position="RB", team="DET", opponent="NO", is_home=True, salary=5000, ownership_pct=ownership_pct
    )


def test_returns_players_unchanged_when_no_ownership_data():
    players = [make_player("Jahmyr Gibbs")]
    result = enrich_with_ownership_pct(players, None)
    assert result == players


def test_fills_in_ownership_pct_by_matching_name():
    players = [make_player("Jahmyr Gibbs")]
    ownership_players = [make_player("Jahmyr Gibbs", ownership_pct=30.5)]

    result = enrich_with_ownership_pct(players, ownership_players)
    assert result[0].ownership_pct == 30.5


def test_leaves_unmatched_player_as_none():
    players = [make_player("Nobody")]
    ownership_players = [make_player("Someone Else", ownership_pct=10.0)]

    result = enrich_with_ownership_pct(players, ownership_players)
    assert result[0].ownership_pct is None


def test_does_not_mutate_original_player_objects():
    players = [make_player("Jahmyr Gibbs")]
    ownership_players = [make_player("Jahmyr Gibbs", ownership_pct=30.5)]

    enrich_with_ownership_pct(players, ownership_players)
    assert players[0].ownership_pct is None
