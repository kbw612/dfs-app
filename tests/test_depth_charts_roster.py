from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team
from backend.services.depth_charts.roster import flatten_offense_roster


def make_snapshot(*teams: Team) -> Snapshot:
    return Snapshot(scraped_at="2026-09-06T00:00:00Z", source_url="https://example.com", teams=list(teams))


def test_none_snapshot_returns_empty_list():
    assert flatten_offense_roster(None) == []


def test_snapshot_with_no_teams_returns_empty_list():
    assert flatten_offense_roster(make_snapshot()) == []


def test_flattens_fantasy_positions_with_one_indexed_rank():
    team = Team(
        team_abbrev="BUF",
        team_name="Buffalo Bills",
        positions={
            "QB": [Player(player="Josh Allen"), Player(player="Backup QB")],
            "RB": [Player(player="James Cook")],
        },
    )
    roster = flatten_offense_roster(make_snapshot(team))

    assert {(p.player, p.position, p.team, p.depth_rank) for p in roster} == {
        ("Josh Allen", "QB", "BUF", 1),
        ("Backup QB", "QB", "BUF", 2),
        ("James Cook", "RB", "BUF", 1),
    }


def test_non_fantasy_positions_are_skipped():
    team = Team(
        team_abbrev="BUF",
        team_name="Buffalo Bills",
        positions={
            "QB": [Player(player="Josh Allen")],
            "DL": [Player(player="Some Lineman")],
            "LB": [Player(player="Some Linebacker")],
        },
    )
    roster = flatten_offense_roster(make_snapshot(team))

    assert [p.player for p in roster] == ["Josh Allen"]


def test_team_missing_a_position_group_contributes_nothing_for_it():
    team = Team(team_abbrev="BUF", team_name="Buffalo Bills", positions={"QB": [Player(player="Josh Allen")]})
    roster = flatten_offense_roster(make_snapshot(team))

    assert [p.position for p in roster] == ["QB"]


def test_team_with_no_abbrev_is_skipped_entirely():
    team = Team(team_abbrev=None, team_name="Unresolved Team", positions={"QB": [Player(player="Some QB")]})
    roster = flatten_offense_roster(make_snapshot(team))

    assert roster == []


def test_covers_every_team_in_the_snapshot():
    bills = Team(team_abbrev="BUF", team_name="Buffalo Bills", positions={"QB": [Player(player="Josh Allen")]})
    dolphins = Team(team_abbrev="MIA", team_name="Miami Dolphins", positions={"QB": [Player(player="Tua Tagovailoa")]})
    roster = flatten_offense_roster(make_snapshot(bills, dolphins))

    assert {(p.player, p.team) for p in roster} == {("Josh Allen", "BUF"), ("Tua Tagovailoa", "MIA")}
