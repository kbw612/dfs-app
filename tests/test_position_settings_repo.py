import json

from backend.repositories.usage_bump.position_settings_repo import load_usage_bump_position_settings


def test_missing_file_returns_empty_dict(tmp_path):
    assert load_usage_bump_position_settings(tmp_path / "does-not-exist.json") == {}


def test_loads_settings(tmp_path):
    path = tmp_path / "usage-bump-position-settings.json"
    path.write_text(
        json.dumps(
            {
                "settings": [
                    {"outPosition": "QB1", "usageBumpPositions": ["QB2"]},
                    {
                        "outPosition": "RB1",
                        "usageBumpPositions": ["RB2", "RB3", "WR1", "WR2", "TE1", "WR3"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    settings = load_usage_bump_position_settings(path)

    assert settings == {
        "QB1": ["QB2"],
        "RB1": ["RB2", "RB3", "WR1", "WR2", "TE1", "WR3"],
    }


def test_skips_entries_missing_out_position(tmp_path):
    path = tmp_path / "usage-bump-position-settings.json"
    path.write_text(
        json.dumps({"settings": [{"usageBumpPositions": ["QB2"]}]}),
        encoding="utf-8",
    )

    assert load_usage_bump_position_settings(path) == {}


def test_missing_usage_bump_positions_defaults_to_empty_list(tmp_path):
    path = tmp_path / "usage-bump-position-settings.json"
    path.write_text(
        json.dumps({"settings": [{"outPosition": "QB1"}]}),
        encoding="utf-8",
    )

    assert load_usage_bump_position_settings(path) == {"QB1": []}
