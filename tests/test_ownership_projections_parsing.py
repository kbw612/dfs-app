from backend.services.ownership.csv_loader import parse_ownership_projections_csv

HEADER = ",Player,Position,Team,Opponent,Salary,% ownership\n"


def csv_text(*rows: str) -> str:
    return HEADER + "".join(rows)


def test_parses_offense_and_dst_rows_from_one_file():
    # Unlike the two-file mock loader, DST rows just show up mixed in with
    # everything else here -- Position is just another column.
    text = csv_text(
        '0,Woody Marks,RB,HOU,ARI,"$5,600",30.5%\n',
        '1,Texans,DST,HOU,ARI,"$3,600",8.8%\n',
    )
    players, messages = parse_ownership_projections_csv(text)

    assert messages == []
    assert [p.player for p in players] == ["Woody Marks", "Texans"]
    assert players[1].position == "DST"


def test_parses_salary_ownership_and_home_away():
    text = csv_text(
        '0,Woody Marks,RB,HOU,ARI,"$5,600",30.5%\n',
        '1,Michael Wilson,WR,ARI,@HOU,"$6,600",11.7%\n',
    )
    players, _ = parse_ownership_projections_csv(text)
    by_name = {p.player: p for p in players}

    assert by_name["Woody Marks"].salary == 5600
    assert by_name["Woody Marks"].ownership_pct == 30.5
    assert by_name["Woody Marks"].is_home is True
    assert by_name["Michael Wilson"].is_home is False


def test_blank_ownership_cell_parses_as_none():
    text = csv_text('0,Woody Marks,RB,HOU,ARI,"$5,600",\n')
    players, messages = parse_ownership_projections_csv(text)

    assert all(m.level != "error" for m in messages)
    assert players[0].ownership_pct is None


def test_malformed_row_skipped_with_warning_others_still_load():
    text = csv_text(
        '0,Woody Marks,RB,HOU,ARI,"$5,600",30.5%\n',
        "1,Bad Data Player,WR,HOU,ARI,N/A,--\n",
    )
    players, messages = parse_ownership_projections_csv(text)

    assert [p.player for p in players] == ["Woody Marks"]
    assert any(m.level == "warning" and "Bad Data Player" in m.message for m in messages)
