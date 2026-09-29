from backend.services.lineup_scenarios.lineup_upload_parser import parse_lineup_upload_csv

SAMPLE_CSV = (
    "QB,RB,RB,WR,WR,WR,TE,FLEX,DST\n"
    "Jared Goff (44220222),Chuba Hubbard (44220330),Bhayshul Tuten (44220340),"
    "Garrett Wilson (44220634),Jameson Williams (44220656),Jaxon Smith-Njigba (44220610),"
    "Sam LaPorta (44221120),George Kittle (44221112),Las Vegas Raiders (44221413)\n"
)


def test_parses_one_lineup_with_nine_players():
    lineups = parse_lineup_upload_csv(SAMPLE_CSV)
    assert len(lineups) == 1
    lineup = lineups[0]
    assert lineup.index == 1
    assert len(lineup.players) == 9


def test_roster_positions_match_header_columns():
    lineups = parse_lineup_upload_csv(SAMPLE_CSV)
    positions = [p.roster_position for p in lineups[0].players]
    assert positions == ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]


def test_strips_trailing_dk_id_suffix_from_names():
    lineups = parse_lineup_upload_csv(SAMPLE_CSV)
    names = [p.name for p in lineups[0].players]
    assert names == [
        "Jared Goff",
        "Chuba Hubbard",
        "Bhayshul Tuten",
        "Garrett Wilson",
        "Jameson Williams",
        "Jaxon Smith-Njigba",
        "Sam LaPorta",
        "George Kittle",
        "Las Vegas Raiders",
    ]


def test_team_starts_unresolved():
    lineups = parse_lineup_upload_csv(SAMPLE_CSV)
    assert all(p.team is None for p in lineups[0].players)


def test_skips_blank_trailing_line():
    csv_text = SAMPLE_CSV + "\n"
    lineups = parse_lineup_upload_csv(csv_text)
    assert len(lineups) == 1
