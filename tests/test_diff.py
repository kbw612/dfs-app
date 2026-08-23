from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team
from backend.services.depth_charts.diff import generate_diff


def make_snapshot(teams: list[Team]) -> Snapshot:
    return Snapshot(
        scraped_at="2026-08-07T08:00:00-04:00",
        source_url="https://example.com",
        teams=teams,
    )


def test_status_change_detected():
    old = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [Player(player="James Conner", status=None)]})]
    )
    new = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [Player(player="James Conner", status="Q")]})]
    )
    changes = generate_diff(old, new)

    assert len(changes) == 1
    change = changes[0]
    assert change.change_types == ["status"]
    assert change.team_abbrev == "ARI"
    assert change.position == "RB"
    assert change.player == "James Conner"
    assert change.previous == {"status": None, "rank": 1}
    assert change.current == {"status": "Q", "rank": 1}


def test_rank_change_detected():
    old = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [
                  Player(player="James Conner", status=None),
                  Player(player="Trey Benson", status=None),
              ]})]
    )
    new = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [
                  Player(player="Trey Benson", status=None),
                  Player(player="James Conner", status=None),
              ]})]
    )
    changes = generate_diff(old, new)

    assert len(changes) == 2
    assert all(c.change_types == ["rank"] for c in changes)
    conner_change = next(c for c in changes if c.player == "James Conner")
    assert conner_change.previous == {"status": None, "rank": 1}
    assert conner_change.current == {"status": None, "rank": 2}


def test_status_and_rank_change_merge_into_one_record():
    """A player who both changes status and shifts rank in the same run
    appears exactly once, with change_types listing both -- status before
    rank."""
    old = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [
                  Player(player="James Conner", status=None),
                  Player(player="Trey Benson", status=None),
              ]})]
    )
    new = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [
                  Player(player="Trey Benson", status=None),
                  Player(player="James Conner", status="Q"),
              ]})]
    )
    changes = generate_diff(old, new)

    conner_changes = [c for c in changes if c.player == "James Conner"]
    assert len(conner_changes) == 1
    assert conner_changes[0].change_types == ["status", "rank"]
    assert conner_changes[0].previous == {"status": None, "rank": 1}
    assert conner_changes[0].current == {"status": "Q", "rank": 2}


def test_added_player_is_other():
    old = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [Player(player="James Conner", status=None)]})]
    )
    new = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [
                  Player(player="James Conner", status=None),
                  Player(player="Trey Benson", status=None),
              ]})]
    )
    changes = generate_diff(old, new)

    added = [c for c in changes if c.player == "Trey Benson"]
    assert len(added) == 1
    assert added[0].change_types == ["other"]
    assert added[0].previous is None
    assert added[0].current == {"status": None, "rank": 2}


def test_removed_player_is_other():
    old = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [
                  Player(player="James Conner", status=None),
                  Player(player="Trey Benson", status=None),
              ]})]
    )
    new = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"RB": [Player(player="James Conner", status=None)]})]
    )
    changes = generate_diff(old, new)

    removed = [c for c in changes if c.player == "Trey Benson"]
    assert len(removed) == 1
    assert removed[0].change_types == ["other"]
    assert removed[0].previous == {"status": None, "rank": 2}
    assert removed[0].current is None


def test_position_change_shows_as_removal_plus_addition_not_matched():
    """A player moving positions (WR -> RB) is not matched across
    positions -- it's a removal from the old position and an addition to
    the new one, per the confirmed design."""
    old = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"WR": [Player(player="Trey Benson", status=None)], "RB": []})]
    )
    new = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals",
              positions={"WR": [], "RB": [Player(player="Trey Benson", status=None)]})]
    )
    changes = generate_diff(old, new)

    assert len(changes) == 2
    assert all(c.change_types == ["other"] for c in changes)
    positions_and_removed = {(c.position, c.previous is None) for c in changes}
    assert ("WR", False) in positions_and_removed  # removed from WR
    assert ("RB", True) in positions_and_removed  # added to RB


def test_defensive_formation_change_is_team_level_other():
    old = make_snapshot(
        [Team(team_abbrev="MIA", team_name="Miami Dolphins",
              defensive_formation="4-3", positions={})]
    )
    new = make_snapshot(
        [Team(team_abbrev="MIA", team_name="Miami Dolphins",
              defensive_formation="3-4", positions={})]
    )
    changes = generate_diff(old, new)

    assert len(changes) == 1
    change = changes[0]
    assert change.change_types == ["other"]
    assert change.field == "defensive_formation"
    assert change.player is None
    assert change.position is None
    assert change.previous == "4-3"
    assert change.current == "3-4"


def test_no_changes_when_snapshots_identical():
    team = Team(team_abbrev="ARI", team_name="Arizona Cardinals", defensive_formation="4-3",
                positions={"RB": [Player(player="James Conner", status="Q")]})
    old = make_snapshot([team])
    new = make_snapshot([team.model_copy(deep=True)])

    assert generate_diff(old, new) == []


def test_team_only_in_one_snapshot_is_skipped_not_guessed_at():
    old = make_snapshot(
        [Team(team_abbrev="ARI", team_name="Arizona Cardinals", positions={})]
    )
    new = make_snapshot(
        [
            Team(team_abbrev="ARI", team_name="Arizona Cardinals", positions={}),
            Team(team_abbrev="ATL", team_name="Atlanta Falcons", positions={}),
        ]
    )
    changes = generate_diff(old, new)

    assert changes == []
