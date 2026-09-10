from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team
from backend.services.ownership.depth_rank import build_depth_rank_lookup
from backend.services.shared.name_match import normalize_player_name


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

    assert lookup[normalize_player_name("Joe Mixon")] == 1
    assert lookup[normalize_player_name("Woody Marks")] == 2
    assert lookup[normalize_player_name("Nico Collins")] == 1


def test_merges_across_teams():
    teams = [
        Team(team_abbrev="HOU", team_name="Texans", positions={"RB": [Player(player="Woody Marks")]}),
        Team(team_abbrev="ARI", team_name="Cardinals", positions={"RB": [Player(player="James Conner")]}),
    ]
    lookup = build_depth_rank_lookup(make_depth_snapshot(teams))

    assert lookup == {normalize_player_name("Woody Marks"): 1, normalize_player_name("James Conner"): 1}


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

    assert lookup[normalize_player_name("Jaylen Waddle")] == 2


def test_unmatched_name_not_in_lookup():
    team = Team(team_abbrev="HOU", team_name="Texans", positions={"RB": [Player(player="Woody Marks")]})
    lookup = build_depth_rank_lookup(make_depth_snapshot([team]))

    assert normalize_player_name("Some Random Player") not in lookup


def test_matches_despite_suffix_and_initial_period_differences():
    # The depth chart and the salary/ownership source don't always agree on
    # "Jr."/"Jr"/no-suffix, or "D.J."/"DJ" -- normalize_player_name() should
    # make both sides land on the same key regardless of which spelling
    # either source used.
    team = Team(
        team_abbrev="IND",
        team_name="Colts",
        positions={
            "WR": [Player(player="Michael Pittman Jr."), Player(player="D.J. Montgomery")],
        },
    )
    lookup = build_depth_rank_lookup(make_depth_snapshot([team]))

    assert lookup[normalize_player_name("Michael Pittman")] == 1
    assert lookup[normalize_player_name("DJ Montgomery")] == 2
