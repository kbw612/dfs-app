from pathlib import Path

from backend.services.ownership.csv_loader import load_ownership_csv

OFFENSE_HEADER = ",Player,Position,Team,Opponent,Salary,% ownership\n"
DST_HEADER = OFFENSE_HEADER


def write_offense_csv(mock_dir: Path, week: int, rows: list[str]) -> None:
    path = mock_dir / f"ownership-projections-week{week}.csv"
    path.write_text(OFFENSE_HEADER + "".join(rows), encoding="utf-8")


def write_dst_csv(mock_dir: Path, week: int, rows: list[str]) -> None:
    path = mock_dir / f"dst-ownership-projections-week{week}.csv"
    path.write_text(DST_HEADER + "".join(rows), encoding="utf-8")


def test_loads_offense_and_dst_rows(tmp_path: Path):
    write_offense_csv(
        tmp_path,
        15,
        ['0,Woody Marks,RB,HOU,ARI,"$5,600",30.5%\n'],
    )
    write_dst_csv(tmp_path, 15, ["0,Texans,DST,HOU,ARI,\"$3,600\",8.8%\n"])

    snapshot, messages = load_ownership_csv(2025, 15, tmp_path)

    assert messages == []
    assert [p.player for p in snapshot.players] == ["Woody Marks", "Texans"]
    assert snapshot.season == 2025
    assert snapshot.week == 15


def test_parses_salary_ownership_and_home_away(tmp_path: Path):
    write_offense_csv(
        tmp_path,
        15,
        [
            '0,Woody Marks,RB,HOU,ARI,"$5,600",30.5%\n',
            '1,Michael Wilson,WR,ARI,@HOU,"$6,600",11.7%\n',
        ],
    )
    snapshot, _ = load_ownership_csv(2025, 15, tmp_path)
    by_name = {p.player: p for p in snapshot.players}

    assert by_name["Woody Marks"].salary == 5600
    assert by_name["Woody Marks"].ownership_pct == 30.5
    assert by_name["Woody Marks"].is_home is True

    assert by_name["Michael Wilson"].opponent == "HOU"
    assert by_name["Michael Wilson"].is_home is False


def test_normalizes_la_team_quirks(tmp_path: Path):
    write_offense_csv(
        tmp_path,
        15,
        [
            '0,Puka Nacua,WR,LA,DET,"$8,700",29.5%\n',
            '1,Justin Herbert,QB,LARC,@KC,"$6,900",12.0%\n',
        ],
    )
    snapshot, _ = load_ownership_csv(2025, 15, tmp_path)
    by_name = {p.player: p for p in snapshot.players}

    assert by_name["Puka Nacua"].team == "LAR"
    assert by_name["Justin Herbert"].team == "LAC"


def test_missing_offense_csv_produces_error_and_empty_snapshot(tmp_path: Path):
    snapshot, messages = load_ownership_csv(2025, 15, tmp_path)

    assert snapshot.players == []
    assert len(messages) == 1
    assert messages[0].level == "error"
    assert "Offense CSV not found" in messages[0].message


def test_missing_dst_csv_warns_but_offense_still_loads(tmp_path: Path):
    write_offense_csv(tmp_path, 15, ['0,Woody Marks,RB,HOU,ARI,"$5,600",30.5%\n'])

    snapshot, messages = load_ownership_csv(2025, 15, tmp_path)

    assert [p.player for p in snapshot.players] == ["Woody Marks"]
    assert any(m.level == "warning" and "DST CSV not found" in m.message for m in messages)


def test_blank_ownership_cell_parses_as_none(tmp_path: Path):
    # DK salaries are typically available before ownership projections --
    # a blank "% ownership" cell shouldn't fail the row. (No DST CSV is
    # written here, hence the expected warning -- see
    # test_missing_dst_csv_warns_but_offense_still_loads -- that's not
    # what this test is checking.)
    write_offense_csv(tmp_path, 15, ['0,Woody Marks,RB,HOU,ARI,"$5,600",\n'])
    snapshot, messages = load_ownership_csv(2025, 15, tmp_path)

    assert all(m.level != "error" for m in messages)
    assert snapshot.players[0].player == "Woody Marks"
    assert snapshot.players[0].salary == 5600
    assert snapshot.players[0].ownership_pct is None


def test_missing_ownership_column_entirely_parses_as_none(tmp_path: Path):
    # A salary-only export (no "% ownership" column at all, not just an
    # empty one) is the realistic early-in-the-week case.
    path = tmp_path / "ownership-projections-week15.csv"
    path.write_text(
        ",Player,Position,Team,Opponent,Salary\n0,Woody Marks,RB,HOU,ARI,\"$5,600\"\n",
        encoding="utf-8",
    )

    snapshot, messages = load_ownership_csv(2025, 15, tmp_path)

    assert all(m.level != "error" for m in messages)
    assert snapshot.players[0].salary == 5600
    assert snapshot.players[0].ownership_pct is None


def test_malformed_row_skipped_with_warning_others_still_load(tmp_path: Path):
    write_offense_csv(
        tmp_path,
        15,
        [
            '0,Woody Marks,RB,HOU,ARI,"$5,600",30.5%\n',
            "1,Bad Data Player,WR,HOU,ARI,N/A,--\n",
        ],
    )
    snapshot, messages = load_ownership_csv(2025, 15, tmp_path)

    assert [p.player for p in snapshot.players] == ["Woody Marks"]
    assert any(
        m.level == "warning" and "Bad Data Player" in m.message for m in messages
    )
