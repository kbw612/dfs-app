import json

from backend.repositories.usage_bump.scoring_matrix_repo import load_bump_matrix


def test_missing_file_returns_empty_dict(tmp_path):
    assert load_bump_matrix(tmp_path / "does-not-exist.json") == {}


def test_loads_and_normalizes_depths_into_sorted_tuple_keys(tmp_path):
    path = tmp_path / "player-out-settings.json"
    path.write_text(
        json.dumps(
            {
                "player_out_settings": [
                    {"player_out_depths": [0], "bump_depth_values": {"1": 1, "2": 0.5}},
                    {"player_out_depths": [2, 1], "bump_depth_values": {"3": 2}},
                ]
            }
        ),
        encoding="utf-8",
    )

    matrix = load_bump_matrix(path)

    assert matrix[(0,)] == {1: 1, 2: 0.5}
    # Unsorted input [2, 1] normalized to a sorted tuple key.
    assert matrix[(1, 2)] == {3: 2}


def test_missing_bump_depth_values_defaults_to_empty_dict(tmp_path):
    path = tmp_path / "player-out-settings.json"
    path.write_text(
        json.dumps({"player_out_settings": [{"player_out_depths": [0]}]}),
        encoding="utf-8",
    )

    assert load_bump_matrix(path) == {(0,): {}}
