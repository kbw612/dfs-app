import json

from backend.repositories.ownership.leverage_tiers_repo import LeverageTier, load_leverage_tiers


def test_missing_file_returns_empty_list(tmp_path):
    assert load_leverage_tiers(tmp_path / "does-not-exist.json") == []


def test_loads_tiers_in_file_order(tmp_path):
    path = tmp_path / "ownership-leverage-tiers.json"
    path.write_text(
        json.dumps(
            {
                "tiers": [
                    {"min_games": 1, "max_games": 1, "leverage_point": 50.0},
                    {"min_games": 2, "max_games": 2, "leverage_point": 40.0},
                    {"min_games": 8, "max_games": None, "leverage_point": 20.0},
                ]
            }
        ),
        encoding="utf-8",
    )

    tiers = load_leverage_tiers(path)

    assert tiers == [
        LeverageTier(min_games=1, max_games=1, leverage_point=50.0),
        LeverageTier(min_games=2, max_games=2, leverage_point=40.0),
        LeverageTier(min_games=8, max_games=None, leverage_point=20.0),
    ]


def test_open_ended_top_tier_has_none_max_games(tmp_path):
    path = tmp_path / "ownership-leverage-tiers.json"
    path.write_text(
        json.dumps({"tiers": [{"min_games": 8, "max_games": None, "leverage_point": 20.0}]}),
        encoding="utf-8",
    )

    tiers = load_leverage_tiers(path)
    assert tiers[0].max_games is None
