from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team
from backend.schemas.star_players.star_players import StarPlayerEntry, StarPlayersResult
from backend.services.injury_report.injury_report_engine import build_injury_report
from backend.services.schedule.schedule_loader import parse_schedule_csv

SCHEDULE_CSV = (
    "Team,Week,Opponent,GameLocation\n"
    "NO,2,DET,Away\n"
    "DET,2,NO,Home\n"
    "ATL,2,CAR,Away\n"
    "CAR,2,ATL,Home\n"
    "KC,2,BYE,\n"
)

NO_STARS = StarPlayersResult()


def _snapshot(*teams: Team) -> Snapshot:
    return Snapshot(scraped_at="2026-09-18T08:00:00-04:00", source_url="https://example.com", teams=list(teams))


def test_groups_healthy_free_teams_are_dropped_and_injured_players_grouped_by_game():
    snapshot = _snapshot(
        Team(
            team_abbrev="DET",
            team_name="Detroit Lions",
            positions={"QB": [Player(player="Jared Goff", status=None)], "WR": [Player(player="Amon-Ra St. Brown", status="Q")]},
        ),
        Team(
            team_abbrev="NO",
            team_name="New Orleans Saints",
            positions={"RB": [Player(player="Alvin Kamara", status="O")]},
        ),
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=NO_STARS)

    assert result.week == 2
    assert result.scraped_at == "2026-09-18T08:00:00-04:00"
    assert len(result.games) == 1
    game = result.games[0]
    assert game.label == "NO @ DET"
    assert game.teams == ["DET", "NO"]
    # Jared Goff (status=None) is excluded -- only the two injured players show.
    names = {p.player for p in game.players}
    assert names == {"Amon-Ra St. Brown", "Alvin Kamara"}


def test_bye_week_team_is_excluded_entirely():
    snapshot = _snapshot(
        Team(team_abbrev="KC", team_name="Kansas City Chiefs", positions={"QB": [Player(player="Patrick Mahomes", status="Q")]})
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=NO_STARS)

    assert result.games == []


def test_team_with_no_schedule_row_is_excluded():
    snapshot = _snapshot(
        Team(team_abbrev="SF", team_name="San Francisco 49ers", positions={"QB": [Player(player="Brock Purdy", status="D")]})
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=NO_STARS)

    assert result.games == []


def test_contest_teams_filters_out_games_not_on_the_slate():
    snapshot = _snapshot(
        Team(team_abbrev="DET", team_name="Detroit Lions", positions={"WR": [Player(player="Amon-Ra St. Brown", status="Q")]}),
        Team(team_abbrev="NO", team_name="New Orleans Saints", positions={"RB": [Player(player="Alvin Kamara", status="O")]}),
        Team(team_abbrev="ATL", team_name="Atlanta Falcons", positions={"QB": [Player(player="Michael Penix Jr.", status="O")]}),
        Team(team_abbrev="CAR", team_name="Carolina Panthers", positions={"RB": [Player(player="Chuba Hubbard", status="Q")]}),
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(
        snapshot, schedule_rows, week=2, star_players=NO_STARS, contest_teams={"ATL", "CAR"}
    )

    assert len(result.games) == 1
    assert result.games[0].teams == ["ATL", "CAR"]


def test_star_flag_is_joined_in_by_team_and_player():
    snapshot = _snapshot(
        Team(team_abbrev="DET", team_name="Detroit Lions", positions={"WR": [Player(player="Amon-Ra St. Brown", status="Q")]}),
        Team(team_abbrev="NO", team_name="New Orleans Saints", positions={"RB": [Player(player="Alvin Kamara", status="O")]}),
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    star_players = StarPlayersResult(players=[StarPlayerEntry(team="DET", player="Amon-Ra St. Brown")])

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=star_players)

    by_name = {p.player: p.starred for p in result.games[0].players}
    assert by_name["Amon-Ra St. Brown"] is True
    assert by_name["Alvin Kamara"] is False


def test_star_flag_does_not_collide_across_teams_with_same_player_name():
    snapshot = _snapshot(
        Team(team_abbrev="DET", team_name="Detroit Lions", positions={"WR": [Player(player="Mike Williams", status="Q")]}),
        Team(team_abbrev="NO", team_name="New Orleans Saints", positions={"WR": [Player(player="Mike Williams", status="O")]}),
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)
    star_players = StarPlayersResult(players=[StarPlayerEntry(team="NO", player="Mike Williams")])

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=star_players)

    by_team = {p.team: p.starred for p in result.games[0].players}
    assert by_team == {"DET": False, "NO": True}


def test_game_with_zero_injured_players_is_dropped():
    snapshot = _snapshot(
        Team(team_abbrev="DET", team_name="Detroit Lions", positions={"QB": [Player(player="Jared Goff", status=None)]}),
        Team(team_abbrev="NO", team_name="New Orleans Saints", positions={"RB": [Player(player="Alvin Kamara", status=None)]}),
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=NO_STARS)

    assert result.games == []


def test_team_abbrev_none_is_skipped_without_erroring():
    snapshot = _snapshot(Team(team_abbrev=None, team_name="Unresolved Team", positions={"QB": [Player(player="X", status="Q")]}))
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=NO_STARS)

    assert result.games == []


def test_depth_is_1_based_index_within_position_array():
    snapshot = _snapshot(
        Team(
            team_abbrev="DET",
            team_name="Detroit Lions",
            positions={
                "RB": [
                    Player(player="Jahmyr Gibbs", status="Q"),
                    Player(player="David Montgomery", status="O"),
                    Player(player="Sione Vaki", status="D"),
                ]
            },
        ),
        Team(team_abbrev="NO", team_name="New Orleans Saints", positions={"RB": [Player(player="Alvin Kamara", status="O")]}),
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=NO_STARS)

    depth_by_name = {p.player: p.depth for p in result.games[0].players}
    assert depth_by_name["Jahmyr Gibbs"] == 1
    assert depth_by_name["David Montgomery"] == 2
    assert depth_by_name["Sione Vaki"] == 3
    assert depth_by_name["Alvin Kamara"] == 1


def test_depth_is_independent_per_position_for_a_multi_position_player():
    snapshot = _snapshot(
        Team(
            team_abbrev="CAR",
            team_name="Carolina Panthers",
            positions={
                "RB": [Player(player="Chuba Hubbard", status="Q"), Player(player="Trevor Etienne", status="Q")],
                "KR": [Player(player="Trevor Etienne", status="Q")],
            },
        ),
        Team(team_abbrev="ATL", team_name="Atlanta Falcons", positions={"QB": [Player(player="Michael Penix Jr.", status="O")]}),
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=NO_STARS)

    depths = {(p.position, p.player): p.depth for p in result.games[0].players}
    assert depths[("RB", "Trevor Etienne")] == 2
    assert depths[("KR", "Trevor Etienne")] == 1


def test_games_sorted_by_label_when_multiple_present():
    snapshot = _snapshot(
        Team(team_abbrev="DET", team_name="Detroit Lions", positions={"WR": [Player(player="Amon-Ra St. Brown", status="Q")]}),
        Team(team_abbrev="NO", team_name="New Orleans Saints", positions={"RB": [Player(player="Alvin Kamara", status="O")]}),
        Team(team_abbrev="ATL", team_name="Atlanta Falcons", positions={"QB": [Player(player="Michael Penix Jr.", status="O")]}),
        Team(team_abbrev="CAR", team_name="Carolina Panthers", positions={"RB": [Player(player="Chuba Hubbard", status="Q")]}),
    )
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV)

    result = build_injury_report(snapshot, schedule_rows, week=2, star_players=NO_STARS)

    labels = [g.label for g in result.games]
    assert labels == sorted(labels)
    assert len(labels) == 2
