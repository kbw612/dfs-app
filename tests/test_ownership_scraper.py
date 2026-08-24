from pathlib import Path

from backend.services.ownership.scraper import parse_players

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "sample_ownership.html").read_text()
NO_TABLE_HTML = "<html><body><p>Please log in</p></body></html>"


def test_parse_players_extracts_expected_rows():
    players, _ = parse_players(FIXTURE_HTML)
    # 7 rows in the fixture -- one has too few cells (silently skipped, no
    # message) and one has unparseable salary/ownership (skipped with a
    # warning) -- so 5 real players make it through.
    assert [p.player for p in players] == [
        "Woody Marks",
        "Michael Wilson",
        "Texans",
        "Puka Nacua",
        "Justin Herbert",
    ]


def test_parse_players_parses_salary_and_ownership():
    players, _ = parse_players(FIXTURE_HTML)
    woody = players[0]
    assert woody.salary == 5600
    assert woody.ownership_pct == 30.5


def test_parse_players_home_away_from_opponent_prefix():
    players, _ = parse_players(FIXTURE_HTML)
    by_name = {p.player: p for p in players}
    assert by_name["Woody Marks"].is_home is True  # "ARI", no @ prefix
    assert by_name["Woody Marks"].opponent == "ARI"
    assert by_name["Michael Wilson"].is_home is False  # "@HOU"
    assert by_name["Michael Wilson"].opponent == "HOU"


def test_parse_players_normalizes_la_team_quirks():
    players, _ = parse_players(FIXTURE_HTML)
    by_name = {p.player: p for p in players}
    # Site quirk: bare "LA" means the Rams here, "LARC" means the Chargers.
    assert by_name["Puka Nacua"].team == "LAR"
    assert by_name["Justin Herbert"].team == "LAC"


def test_parse_players_dst_is_just_another_position():
    players, _ = parse_players(FIXTURE_HTML)
    texans = next(p for p in players if p.player == "Texans")
    assert texans.position == "DST"


def test_parse_players_skips_row_with_too_few_cells_silently():
    players, messages = parse_players(FIXTURE_HTML)
    assert "Too Few Cells" not in [p.player for p in players]
    assert not any("Too Few Cells" in m.message for m in messages)


def test_parse_players_warns_and_skips_unparseable_row():
    _, messages = parse_players(FIXTURE_HTML)
    assert any(
        m.level == "warning" and "Bad Data Player" in m.message for m in messages
    )


def test_parse_players_missing_table_produces_error_message():
    players, messages = parse_players(NO_TABLE_HTML)
    assert players == []
    assert len(messages) == 1
    assert messages[0].level == "error"
    assert "table_1" in messages[0].message
