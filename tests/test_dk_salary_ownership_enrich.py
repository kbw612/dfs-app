from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct


def make_player(player, ownership_pct=None, position="RB", team="DET"):
    return OwnershipPlayer(
        player=player, position=position, team=team, opponent="NO", is_home=True, salary=5000, ownership_pct=ownership_pct
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


def test_dst_matches_by_team_not_name():
    # DK's salary export names a DST by nickname alone ("Ravens"); the
    # Ownership projections file spells it out in full ("Baltimore
    # Ravens") -- an exact-name match would always miss, so DST rows
    # match on team abbreviation instead.
    players = [make_player("Ravens", position="DST", team="BAL")]
    ownership_players = [
        make_player("Baltimore Ravens", ownership_pct=8.36, position="DST", team="BAL")
    ]

    result = enrich_with_ownership_pct(players, ownership_players)
    assert result[0].ownership_pct == 8.36


def test_dst_team_match_does_not_leak_into_offense_name_match():
    # An offense player sharing a team with a DST shouldn't accidentally
    # pick up that DST's ownership_pct via the team-keyed lookup -- only
    # DST rows use the team-based path.
    players = [make_player("Derrick Henry", position="RB", team="BAL")]
    ownership_players = [
        make_player("Baltimore Ravens", ownership_pct=8.36, position="DST", team="BAL"),
        make_player("Derrick Henry", ownership_pct=22.19, position="RB", team="BAL"),
    ]

    result = enrich_with_ownership_pct(players, ownership_players)
    assert result[0].ownership_pct == 22.19


def test_dst_leaves_unmatched_team_as_none():
    players = [make_player("Ravens", position="DST", team="BAL")]
    ownership_players = [make_player("Denver Broncos", ownership_pct=6.51, position="DST", team="DEN")]

    result = enrich_with_ownership_pct(players, ownership_players)
    assert result[0].ownership_pct is None
