from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team
from backend.services.ownership.depth_rank import build_depth_rank_lookup


def make_depth_snapshot(teams: list[Team]) -> Snapshot:
    return Snapshot(scraped_at="2026-08-23T10:00:00-04:00", source_url="https://example.com", teams=teams)


def test_returns_empty_lookup_for_none_snapshot():
    assert build_depth_rank_lookup(None) == {}


def test_looks_up_rank_by_position_and_index():
    team = Team(
        team_abbrev="HOU",
        team_name="Texans",
        positions={
            "RB": [Player(player="Joe Mixon"), Player(player="Woody Marks")],
            "WR": [Player(player="Nico Collins")],
        },
    )
    lookup = build_depth_rank_lookup(make_depth_snapshot([team]))

    assert lookup["Joe Mixon"] == 1
    assert lookup["Woody Marks"] == 2
    assert lookup["Nico Collins"] == 1


def test_merges_across_teams():
    teams = [
        Team(team_abbrev="HOU", team_name="Texans", positions={"RB": [Player(player="Woody Marks")]}),
        Team(team_abbrev="ARI", team_name="Cardinals", positions={"RB": [Player(player="James Conner")]}),
    ]
    lookup = build_depth_rank_lookup(make_depth_snapshot(teams))

    assert lookup == {"Woody Marks": 1, "James Conner": 1}


def test_offensive_fantasy_listing_wins_for_two_way_players():
    # Same name listed at WR (rank 2) and also as a punt returner (rank 1)
    # -- the WR listing should win since that's what ownership data cares
    # about, matching usage_bump/engine.py's _build_location tie-break.
    team = Team(
        team_abbrev="MIA",
        team_name="Dolphins",
        positions={
            "PR": [Player(player="Jaylen Waddle")],
            "WR": [Player(player="Tyreek Hill"), Player(player="Jaylen Waddle")],
        },
    )
    lookup = build_depth_rank_lookup(make_depth_snapshot([team]))

    assert lookup["Jaylen Waddle"] == 2


def test_unmatched_name_not_in_lookup():
    team = Team(team_abbrev="HOU", team_name="Texans", positions={"RB": [Player(player="Woody Marks")]})
    lookup = build_depth_rank_lookup(make_depth_snapshot([team]))

    assert "Some Random Player" not in lookup
