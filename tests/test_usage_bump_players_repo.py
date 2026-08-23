import json

from backend.repositories.usage_bump.usage_bump_players_repo import load_usage_bump_players


def test_missing_file_returns_empty_dict(tmp_path):
    assert load_usage_bump_players(tmp_path / "does-not-exist.json") == {}


def test_loads_teams_and_players(tmp_path):
    path = tmp_path / "usage-bump-players.json"
    path.write_text(
        json.dumps(
            {
                "teams": [
                    {
                        "teamAbbrev": "CAR",
                        "players": [
                            {
                                "name": "Jalen Coker",
                                "moreUsagePlayers": ["Tetairoa McMillan", "Xavier Legette"],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    players = load_usage_bump_players(path)

    assert players == {("CAR", "Jalen Coker"): ["Tetairoa McMillan", "Xavier Legette"]}


def test_skips_entries_missing_team_abbrev_or_name(tmp_path):
    path = tmp_path / "usage-bump-players.json"
    path.write_text(
        json.dumps(
            {
                "teams": [
                    {"players": [{"name": "No Team Abbrev", "moreUsagePlayers": []}]},
                    {"teamAbbrev": "MIA", "players": [{"moreUsagePlayers": ["X"]}]},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_usage_bump_players(path) == {}


def test_missing_more_usage_players_defaults_to_empty_list(tmp_path):
    path = tmp_path / "usage-bump-players.json"
    path.write_text(
        json.dumps({"teams": [{"teamAbbrev": "MIA", "players": [{"name": "Someone"}]}]}),
        encoding="utf-8",
    )

    assert load_usage_bump_players(path) == {("MIA", "Someone"): []}
