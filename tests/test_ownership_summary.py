from backend.schemas.ownership.ownership import OwnershipProjectionsPlayer
from backend.services.ownership.ownership_summary import (
    compute_game_ownership_rollups,
    compute_team_ownership_rollups,
)


def make_player(player, position, team, opponent, ownership_pct, initial_ownership_pct=None):
    return OwnershipProjectionsPlayer(
        player=player,
        position=position,
        team=team,
        opponent=opponent,
        salary=6000,
        ownership_pct=ownership_pct,
        initial_ownership_pct=initial_ownership_pct,
    )


# -- compute_team_ownership_rollups --


def test_team_rollup_sums_non_dst_players_excludes_dst():
    players = [
        make_player("QB1", "QB", "SF", "DEN", 40.0, 35.0),
        make_player("RB1", "RB", "SF", "DEN", 20.0, 15.0),
        make_player("DST1", "DST", "SF", "DEN", 15.0, 15.0),
    ]
    rollups = compute_team_ownership_rollups(players, {})
    sf = next(r for r in rollups if r.team == "SF")
    assert sf.total_ownership_pct == 60.0
    assert sf.initial_total_ownership_pct == 50.0


def test_team_rollup_treats_missing_ownership_as_zero():
    players = [
        make_player("QB1", "QB", "SF", "DEN", None, None),
        make_player("RB1", "RB", "SF", "DEN", 20.0, 10.0),
    ]
    rollups = compute_team_ownership_rollups(players, {})
    sf = next(r for r in rollups if r.team == "SF")
    assert sf.total_ownership_pct == 20.0
    assert sf.initial_total_ownership_pct == 10.0


def test_team_rollup_omits_team_with_only_dst_row():
    players = [make_player("DST1", "DST", "SF", "DEN", 15.0, 15.0)]
    rollups = compute_team_ownership_rollups(players, {})
    assert all(r.team != "SF" for r in rollups)


def test_team_rollup_actual_is_none_without_contest_data():
    players = [make_player("QB1", "QB", "SF", "DEN", 40.0, 40.0)]
    rollups = compute_team_ownership_rollups(players, {})
    sf = next(r for r in rollups if r.team == "SF")
    assert sf.actual_total_ownership_pct is None


def test_team_rollup_actual_can_be_a_real_zero_once_contest_data_exists():
    players = [make_player("QB1", "QB", "SF", "DEN", 40.0, 40.0)]
    # Contest data exists for some other player, so SF's own actual sum
    # (0.0, since QB1 has no entry) is a real number, not "unknown."
    rollups = compute_team_ownership_rollups(players, {"SOMEONE_ELSE": 12.0})
    sf = next(r for r in rollups if r.team == "SF")
    assert sf.actual_total_ownership_pct == 0.0


def test_team_rollup_sums_actual_ownership_by_player():
    players = [
        make_player("QB1", "QB", "SF", "DEN", 40.0, 40.0),
        make_player("RB1", "RB", "SF", "DEN", 20.0, 20.0),
    ]
    rollups = compute_team_ownership_rollups(players, {"QB1": 30.0, "RB1": 10.0})
    sf = next(r for r in rollups if r.team == "SF")
    assert sf.actual_total_ownership_pct == 40.0


# -- compute_game_ownership_rollups --


def test_game_rollup_groups_both_teams_under_one_key():
    players = [
        make_player("QB1", "QB", "SF", "DEN", 40.0, 40.0),
        make_player("QB2", "QB", "DEN", "SF", 30.0, 30.0),
    ]
    rollups = compute_game_ownership_rollups(players, {}, {})
    assert len(rollups) == 1
    game = rollups[0]
    assert game.total_ownership_pct == 70.0
    assert len(game.players) == 2


def test_game_rollup_includes_dst_in_players_list_but_not_totals():
    players = [
        make_player("QB1", "QB", "SF", "DEN", 40.0, 40.0),
        make_player("DST1", "DST", "SF", "DEN", 15.0, 15.0),
    ]
    rollups = compute_game_ownership_rollups(players, {}, {})
    game = rollups[0]
    assert game.total_ownership_pct == 40.0
    assert len(game.players) == 2


def test_game_rollup_resolves_home_away_from_home_by_team():
    players = [
        make_player("QB1", "QB", "SF", "DEN", 40.0, 40.0),
        make_player("QB2", "QB", "DEN", "SF", 30.0, 30.0),
    ]
    rollups = compute_game_ownership_rollups(players, {"SF": False, "DEN": True}, {})
    game = rollups[0]
    assert game.away_team == "SF"
    assert game.home_team == "DEN"


def test_game_rollup_home_away_none_when_unresolved():
    players = [make_player("QB1", "QB", "SF", "DEN", 40.0, 40.0)]
    rollups = compute_game_ownership_rollups(players, {}, {})
    game = rollups[0]
    assert game.away_team is None
    assert game.home_team is None


def test_game_rollup_actual_none_without_contest_data():
    players = [make_player("QB1", "QB", "SF", "DEN", 40.0, 40.0)]
    rollups = compute_game_ownership_rollups(players, {}, {})
    assert rollups[0].actual_total_ownership_pct is None


def test_game_rollup_players_sorted_by_ownership_descending():
    players = [
        make_player("Low", "WR", "SF", "DEN", 10.0, 10.0),
        make_player("High", "QB", "SF", "DEN", 40.0, 40.0),
    ]
    rollups = compute_game_ownership_rollups(players, {}, {})
    names = [p.player for p in rollups[0].players]
    assert names == ["High", "Low"]
