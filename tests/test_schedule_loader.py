from backend.services.schedule.schedule_loader import games_for_week, opponent_and_location, parse_schedule_csv

SCHEDULE_CSV = (
    "Team,Week,Opponent,GameLocation\n"
    "TEN,14,CLE,Away\n"
    "CLE,14,TEN,Home\n"
    "SF,14,BYE,Home\n"
    "KC,14,DEN,Home\n"
    "DEN,14,KC,Away\n"
)


def test_parse_schedule_csv_reads_every_row():
    rows = parse_schedule_csv(SCHEDULE_CSV)
    assert len(rows) == 5
    ten = next(r for r in rows if r.team == "TEN")
    assert ten.week == 14
    assert ten.opponent == "CLE"
    assert ten.game_location == "Away"


def test_parse_schedule_csv_skips_blank_rows():
    csv_text = "Team,Week,Opponent,GameLocation\n,,, \nTEN,14,CLE,Away\n"
    rows = parse_schedule_csv(csv_text)
    assert len(rows) == 1


def test_opponent_and_location_finds_matching_team_week():
    rows = parse_schedule_csv(SCHEDULE_CSV)
    assert opponent_and_location(rows, "TEN", 14) == ("CLE", "Away")
    assert opponent_and_location(rows, "CLE", 14) == ("TEN", "Home")


def test_opponent_and_location_normalizes_bye_week():
    rows = parse_schedule_csv(SCHEDULE_CSV)
    # SF's raw row says GameLocation=Home for its own BYE row -- normalized
    # to ("BYE", "BYE") regardless.
    assert opponent_and_location(rows, "SF", 14) == ("BYE", "BYE")


def test_opponent_and_location_none_when_no_matching_row():
    rows = parse_schedule_csv(SCHEDULE_CSV)
    assert opponent_and_location(rows, "TEN", 15) is None
    assert opponent_and_location([], "TEN", 14) is None


def test_games_for_week_collapses_both_sides_of_matchup():
    rows = parse_schedule_csv(SCHEDULE_CSV)
    games = games_for_week(rows, 14)
    assert frozenset({"TEN", "CLE"}) in games
    assert frozenset({"KC", "DEN"}) in games
    assert len(games) == 2  # BYE contributes nothing


def test_games_for_week_empty_for_week_with_no_rows():
    rows = parse_schedule_csv(SCHEDULE_CSV)
    assert games_for_week(rows, 1) == []


def test_parse_schedule_csv_normalizes_jac_to_jax():
    # Some schedule exports spell Jacksonville "JAC" -- the DK Players
    # tracker (and every other team-keyed lookup in this app) always uses
    # "JAX", so both the Team column and a non-BYE Opponent column need
    # normalizing or that team's players silently never match when its
    # game is selected in the Game Logs tab.
    csv_text = "Team,Week,Opponent,GameLocation\nJAC,14,NYJ,Home\nNYJ,14,JAC,Away\n"
    rows = parse_schedule_csv(csv_text)
    jax = next(r for r in rows if r.team == "JAX")
    assert jax.opponent == "NYJ"
    nyj = next(r for r in rows if r.team == "NYJ")
    assert nyj.opponent == "JAX"


def test_parse_schedule_csv_leaves_bye_opponent_untouched():
    csv_text = "Team,Week,Opponent,GameLocation\nJAC,14,BYE,Home\n"
    rows = parse_schedule_csv(csv_text)
    assert rows[0].team == "JAX"
    assert rows[0].opponent == "BYE"
