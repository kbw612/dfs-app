from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team
from backend.schemas.star_players.star_players import StarPlayerEntry, StarPlayersResult
from backend.services.game_preview.game_preview_injuries import build_team_injury_groups


def _snapshot(teams: list[Team]) -> Snapshot:
    return Snapshot(scraped_at="2026-01-01T00:00:00", source_url="http://x", teams=teams)


def _group(groups, label):
    return next(g for g in groups if g.label == label)


def test_no_row_for_team_gives_empty_list():
    snapshot = _snapshot([Team(team_abbrev="DEN", team_name="Broncos", positions={})])
    groups = build_team_injury_groups("LAC", snapshot, StarPlayersResult())
    assert groups == []


def test_fully_healthy_team_gives_empty_list():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={"QB": [Player(player="Justin Herbert", status=None)]},
    )
    groups = build_team_injury_groups("LAC", _snapshot([team]), StarPlayersResult())
    assert groups == []


def test_ol_group_depth_one_and_two():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={
            "LT": [
                Player(player="Starter LT", status="O"),
                Player(player="Backup LT", status="Q"),
                Player(player="Third String LT", status="Q"),
            ]
        },
    )
    groups = build_team_injury_groups("LAC", _snapshot([team]), StarPlayersResult())
    ol_group = _group(groups, "O-Line (depth 1-2)")
    names = {e.player for e in ol_group.entries}
    assert names == {"Starter LT", "Backup LT"}
    assert "Third String LT" not in names
    entry = next(e for e in ol_group.entries if e.player == "Starter LT")
    assert entry.position == "LT"
    assert entry.depth == 1
    assert entry.status == "O"


def test_defensive_front_combines_dl_and_lb():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={
            "LDE": [Player(player="Starter DE", status="O")],
            "MLB": [Player(player="Starter MLB", status="Q")],
        },
    )
    groups = build_team_injury_groups("LAC", _snapshot([team]), StarPlayersResult())
    front_group = _group(groups, "Defensive Front (depth 1-2)")
    names = {e.player for e in front_group.entries}
    assert names == {"Starter DE", "Starter MLB"}


def test_defensive_front_depth_one_and_two_only():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={
            "LDE": [
                Player(player="Starter DE", status="O"),
                Player(player="Backup DE", status="Q"),
                Player(player="Third String DE", status="Q"),
            ]
        },
    )
    groups = build_team_injury_groups("LAC", _snapshot([team]), StarPlayersResult())
    front_group = _group(groups, "Defensive Front (depth 1-2)")
    names = {e.player for e in front_group.entries}
    assert names == {"Starter DE", "Backup DE"}
    assert "Third String DE" not in names


def test_defensive_backs_depth_one_and_two():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={
            "LCB": [
                Player(player="Starter CB", status="O"),
                Player(player="Backup CB", status="Q"),
                Player(player="Third String CB", status="Q"),
            ]
        },
    )
    groups = build_team_injury_groups("LAC", _snapshot([team]), StarPlayersResult())
    db_group = _group(groups, "Defensive Backs (depth 1-2)")
    names = {e.player for e in db_group.entries}
    assert names == {"Starter CB", "Backup CB"}
    assert "Third String CB" not in names


def test_skill_positions_depth_one_through_four():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={
            "WR": [
                Player(player="WR1", status="O"),
                Player(player="WR2", status=None),
                Player(player="WR3", status="Q"),
                Player(player="WR4", status="D"),
                Player(player="WR5", status="O"),
            ]
        },
    )
    groups = build_team_injury_groups("LAC", _snapshot([team]), StarPlayersResult())
    skill_group = _group(groups, "Skill Positions (depth 1-4)")
    names = {e.player for e in skill_group.entries}
    assert names == {"WR1", "WR3", "WR4"}
    assert "WR5" not in names


def test_starred_flag_set_on_qualifying_entry():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={"LT": [Player(player="Star LT", status="O")]},
    )
    star_players = StarPlayersResult(players=[StarPlayerEntry(team="LAC", player="Star LT")])
    groups = build_team_injury_groups("LAC", _snapshot([team]), star_players)
    ol_group = _group(groups, "O-Line (depth 1-2)")
    entry = ol_group.entries[0]
    assert entry.player == "Star LT"
    assert entry.starred is True


def test_non_starred_entry_has_starred_false():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={"LT": [Player(player="Regular LT", status="O")]},
    )
    groups = build_team_injury_groups("LAC", _snapshot([team]), StarPlayersResult())
    ol_group = _group(groups, "O-Line (depth 1-2)")
    assert ol_group.entries[0].starred is False


def test_star_players_scoped_to_their_own_team():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={"WR": [Player(player="Some WR", status="Q")]},
    )
    star_players = StarPlayersResult(players=[StarPlayerEntry(team="DEN", player="Some WR")])
    groups = build_team_injury_groups("LAC", _snapshot([team]), star_players)
    skill_group = _group(groups, "Skill Positions (depth 1-4)")
    assert skill_group.entries[0].starred is False


def test_starred_player_past_every_groups_depth_cutoff_does_not_appear():
    team = Team(
        team_abbrev="LAC",
        team_name="Chargers",
        positions={
            "WR": [
                Player(player="WR1", status=None),
                Player(player="WR2", status=None),
                Player(player="WR3", status=None),
                Player(player="WR4", status=None),
                Player(player="Deep Star WR5", status="Q"),
            ]
        },
    )
    star_players = StarPlayersResult(players=[StarPlayerEntry(team="LAC", player="Deep Star WR5")])
    groups = build_team_injury_groups("LAC", _snapshot([team]), star_players)
    assert groups == []
