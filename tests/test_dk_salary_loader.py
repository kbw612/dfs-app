from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv

HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status"


def csv_text(*rows: str) -> str:
    return "\n".join([HEADER, *rows])


def test_parses_offense_row():
    text = csv_text(
        "RB,Jahmyr Gibbs (43727325),Jahmyr Gibbs,43727325,RB/FLEX,8000,NO@DET 09/13/2026 01:00PM ET,DET,22.3,"
    )
    snapshot, messages = parse_dk_salary_csv(text, 2026, 1)

    assert len(snapshot.players) == 1
    player = snapshot.players[0]
    assert player.player == "Jahmyr Gibbs"
    assert player.position == "RB"
    assert player.team == "DET"
    assert player.opponent == "NO"
    assert player.is_home is True
    assert player.salary == 8000
    assert player.ownership_pct is None
    assert messages == []


def test_parses_dst_row():
    text = csv_text("DST,Chargers (43728525),Chargers,43728525,DST,3500,ARI@LAC 09/13/2026 04:25PM ET,LAC,6.7,")
    snapshot, _ = parse_dk_salary_csv(text, 2026, 1)

    player = snapshot.players[0]
    assert player.player == "Chargers"
    assert player.position == "DST"
    assert player.team == "LAC"
    assert player.opponent == "ARI"
    assert player.is_home is True


def test_skips_unparseable_row_with_warning():
    text = csv_text(
        "RB,Good Player (1),Good Player,1,RB/FLEX,5000,NO@DET 09/13/2026 01:00PM ET,DET,10,",
        "RB,Bad Player (2),Bad Player,2,RB/FLEX,not-a-number,NO@DET 09/13/2026 01:00PM ET,DET,10,",
    )
    snapshot, messages = parse_dk_salary_csv(text, 2026, 1)

    assert [p.player for p in snapshot.players] == ["Good Player"]
    assert any(m.level == "warning" and "Bad Player" in m.message for m in messages)


def test_empty_csv_produces_error_message():
    snapshot, messages = parse_dk_salary_csv(HEADER, 2026, 1)
    assert snapshot.players == []
    assert any(m.level == "error" for m in messages)


def test_snapshot_has_season_and_week():
    text = csv_text(
        "QB,Josh Allen (1),Josh Allen,1,QB,7000,BUF@HOU 09/13/2026 01:00PM ET,BUF,23.3,"
    )
    snapshot, _ = parse_dk_salary_csv(text, 2026, 1)
    assert snapshot.season == 2026
    assert snapshot.week == 1
