from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.ownership.ownership_totals import sum_current_ownership_pct


def make_player(player, position, team, ownership_pct):
    return OwnershipPlayer(
        player=player,
        position=position,
        team=team,
        opponent="OPP",
        salary=6000,
        ownership_pct=ownership_pct,
    )


def test_sum_current_ownership_pct_sums_non_dst_players():
    players = [
        make_player("QB1", "QB", "SF", 40.0),
        make_player("RB1", "RB", "SF", 20.0),
        make_player("DST1", "DST", "SF", 15.0),
    ]
    assert sum_current_ownership_pct("SF", players) == 60.0


def test_sum_current_ownership_pct_treats_missing_ownership_as_zero():
    players = [
        make_player("QB1", "QB", "SF", None),
        make_player("RB1", "RB", "SF", 20.0),
    ]
    assert sum_current_ownership_pct("SF", players) == 20.0


def test_sum_current_ownership_pct_none_when_no_matching_non_dst_rows():
    players = [make_player("DST1", "DST", "SF", 15.0)]
    assert sum_current_ownership_pct("SF", players) is None


def test_sum_current_ownership_pct_ignores_other_teams():
    players = [
        make_player("QB1", "QB", "SF", 40.0),
        make_player("QB2", "QB", "DEN", 30.0),
    ]
    assert sum_current_ownership_pct("SF", players) == 40.0
