from backend.schemas.game_environment.game_environment import GameEnvironmentEntry
from backend.services.game_environment.scoring import score_game_environment, team_implied_total


def make_entry(**overrides) -> GameEnvironmentEntry:
    fields = dict(
        season=2025,
        week=9,
        game_key="BUF-NO",
        home_team="BUF",
        away_team="NO",
        home_spread=-3.5,
        over_under=45.0,
        home_implied_total=24.0,
        away_implied_total=20.5,
    )
    fields.update(overrides)
    return GameEnvironmentEntry(**fields)


def test_team_implied_total_returns_home_total_for_home_team():
    entry = make_entry(home_implied_total=27.0, away_implied_total=20.0)
    assert team_implied_total(entry, "BUF") == 27.0


def test_team_implied_total_returns_away_total_for_away_team():
    entry = make_entry(home_implied_total=27.0, away_implied_total=20.0)
    assert team_implied_total(entry, "NO") == 20.0


def test_team_implied_total_none_for_unrelated_team():
    entry = make_entry()
    assert team_implied_total(entry, "KC") is None


def test_score_none_when_no_team_total():
    assert score_game_environment(None, over_under=50.0) is None


def test_score_top_tier_at_24_or_more():
    assert score_game_environment(24.0, over_under=None) == 3.0
    assert score_game_environment(30.0, over_under=None) == 3.0


def test_score_top_tier_via_22_plus_with_47_plus_over_under():
    assert score_game_environment(22.0, over_under=47.0) == 3.0
    assert score_game_environment(23.5, over_under=50.0) == 3.0


def test_score_not_top_tier_when_22_plus_but_over_under_below_47():
    # 22-23.99 without a 47+ O/U doesn't qualify for the top tier -- falls
    # to the middle tier instead.
    assert score_game_environment(22.0, over_under=46.5) == 2.0


def test_score_middle_tier_20_to_23_75():
    assert score_game_environment(20.0, over_under=None) == 2.0
    assert score_game_environment(23.75, over_under=None) == 2.0


def test_score_middle_tier_covers_gap_up_to_24():
    # 23.75-24 isn't explicitly named by the rule, but reads as still
    # "the middle band" rather than unscored -- see scoring.py's docstring.
    assert score_game_environment(23.9, over_under=None) == 2.0


def test_score_bottom_tier_19_or_less():
    assert score_game_environment(19.0, over_under=None) == 1.0
    assert score_game_environment(10.0, over_under=None) == 1.0


def test_score_bottom_tier_covers_gap_below_20():
    assert score_game_environment(19.5, over_under=None) == 1.0


def test_score_missing_over_under_still_resolves_from_team_total_alone():
    assert score_game_environment(25.0, over_under=None) == 3.0
    assert score_game_environment(15.0, over_under=None) == 1.0
