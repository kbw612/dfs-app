import json

from backend.repositories.usage_bump.usage_bump_players_repo import (
    load_usage_bump_players,
    load_usage_bump_players_file,
    save_usage_bump_players_file,
)
from backend.schemas.usage_bump.usage_bump_players import (
    UsageBumpPlayerEntry,
    UsageBumpPlayersResult,
    UsageBumpTeamEntry,
)


def test_missing_file_returns_empty_dict(tmp_path):
    assert load_usage_bump_players(tmp_path / "does-not-exist.json") == {}


def test_loads_teams_and_players(tmp_path):
    path = tmp_path / "usage_bump_players.json"
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
    path = tmp_path / "usage_bump_players.json"
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
    path = tmp_path / "usage_bump_players.json"
    path.write_text(
        json.dumps({"teams": [{"teamAbbrev": "MIA", "players": [{"name": "Someone"}]}]}),
        encoding="utf-8",
    )

    assert load_usage_bump_players(path) == {("MIA", "Someone"): []}


# -- load_usage_bump_players_file / save_usage_bump_players_file -------------
#
# The structured (nested) read/write used by the Usage Bump Players tab's
# own GET/PUT /api/usage-bump-players -- see this module's own docstring
# for why load_usage_bump_players (above) is built on top of this instead
# of duplicating the parsing.


def test_load_usage_bump_players_file_missing_file_returns_empty_teams(tmp_path):
    result = load_usage_bump_players_file(tmp_path / "does-not-exist.json")
    assert result == UsageBumpPlayersResult(teams=[])


def test_load_usage_bump_players_file_preserves_nested_shape_and_order(tmp_path):
    path = tmp_path / "usage_bump_players.json"
    path.write_text(
        json.dumps(
            {
                "teams": [
                    {
                        "teamAbbrev": "CAR",
                        "players": [
                            {"name": "Jalen Coker", "moreUsagePlayers": ["Tetairoa McMillan", "Xavier Legette"]}
                        ],
                    },
                    {"teamAbbrev": "TB", "players": [{"name": "Emeka Egbuka", "moreUsagePlayers": ["Mike Evans"]}]},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = load_usage_bump_players_file(path)

    assert result == UsageBumpPlayersResult(
        teams=[
            UsageBumpTeamEntry(
                teamAbbrev="CAR",
                players=[
                    UsageBumpPlayerEntry(name="Jalen Coker", moreUsagePlayers=["Tetairoa McMillan", "Xavier Legette"])
                ],
            ),
            UsageBumpTeamEntry(
                teamAbbrev="TB", players=[UsageBumpPlayerEntry(name="Emeka Egbuka", moreUsagePlayers=["Mike Evans"])]
            ),
        ]
    )


def test_load_usage_bump_players_file_skips_malformed_entries(tmp_path):
    # Same lenient skip behavior as load_usage_bump_players -- a team with
    # no teamAbbrev, or a player with no name, is dropped rather than
    # raising.
    path = tmp_path / "usage_bump_players.json"
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

    result = load_usage_bump_players_file(path)

    # The team-less block is dropped entirely; the MIA block survives but
    # with its one malformed (nameless) player entry dropped too.
    assert result == UsageBumpPlayersResult(teams=[UsageBumpTeamEntry(teamAbbrev="MIA", players=[])])


def test_save_usage_bump_players_file_then_load_round_trips(tmp_path):
    path = tmp_path / "nested" / "usage_bump_players.json"
    data = UsageBumpPlayersResult(
        teams=[
            UsageBumpTeamEntry(
                teamAbbrev="LV",
                players=[
                    UsageBumpPlayerEntry(name="Brock Bowers", moreUsagePlayers=["Ashton Jeanty"]),
                    UsageBumpPlayerEntry(name="Ashton Jeanty", moreUsagePlayers=[]),
                ],
            )
        ]
    )

    save_usage_bump_players_file(path, data)

    assert load_usage_bump_players_file(path) == data
    assert path.exists()  # also confirms parent dirs were created


def test_save_usage_bump_players_file_overwrites_prior_contents(tmp_path):
    path = tmp_path / "usage_bump_players.json"
    save_usage_bump_players_file(
        path, UsageBumpPlayersResult(teams=[UsageBumpTeamEntry(teamAbbrev="CAR", players=[])])
    )
    save_usage_bump_players_file(
        path, UsageBumpPlayersResult(teams=[UsageBumpTeamEntry(teamAbbrev="TB", players=[])])
    )

    result = load_usage_bump_players_file(path)
    assert [team.teamAbbrev for team in result.teams] == ["TB"]
