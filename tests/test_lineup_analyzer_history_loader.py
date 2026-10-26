import pytest

from backend.services.lineup_analyzer.history_loader import load_week, parse_projections

SALARY = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"
    "QB,Pat Mahomes (1),Pat Mahomes,1,QB,8000,KC@LV 09/14/2025 04:25PM ET,KC,20\n"
    "RB,Rb One (2),Rb One,2,RB/FLEX,7000,KC@LV 09/14/2025 04:25PM ET,KC,15\n"
    "RB,Rb Two (3),Rb Two,3,RB/FLEX,5000,KC@LV 09/14/2025 04:25PM ET,LV,10\n"
    "WR,Wr One (4),Wr One,4,WR/FLEX,6000,KC@LV 09/14/2025 04:25PM ET,KC,12\n"
    "WR,Wr Two (5),Wr Two,5,WR/FLEX,5500,KC@LV 09/14/2025 04:25PM ET,LV,11\n"
    "WR,Wr Three (6),Wr Three,6,WR/FLEX,4500,KC@LV 09/14/2025 04:25PM ET,LV,9\n"
    "TE,Te One (7),Te One,7,TE/FLEX,4000,KC@LV 09/14/2025 04:25PM ET,KC,8\n"
    "DST,Chiefs  (8),Chiefs ,8,DST,3000,KC@LV 09/14/2025 04:25PM ET,KC,7\n"
    "WR,Off Slate (9),Off Slate,9,WR/FLEX,7000,DAL@NYG 09/14/2025 01:00PM ET,DAL,15\n"
)
STANDINGS = (
    "Rank,EntryId,EntryName,TimeRemaining,Points,Lineup,,Player,Roster Position,%Drafted,FPTS\n"
    "1,11,a (1/1),0,200.5,DST Chiefs  FLEX Wr Three QB Pat Mahomes RB Rb One RB Rb Two TE Te One WR Wr One WR Wr Two WR Wr Three,,Pat Mahomes,QB,30.00%,25.0\n"
    "2,12,b (1/1),0,190.0,DST Chiefs  FLEX Rb Two QB Pat Mahomes RB Rb One RB Rb Two TE Te One WR Wr One WR Wr Two WR Nobody Known,,,,,\n"
)
PLAYERS = (
    "Name,Position,Roster Position,TeamAbbrev,Week,Salary,%Drafted,FPTS,Non_TD_FPTS,TD_FPTS\n"
    "Pat Mahomes,QB,QB,KC,3,8000,30.00%,25.0,25.0,0.0\n"
    "Rb One,RB,RB/FLEX,KC,3,7000,12.50%,14.0,14.0,0.0\n"
    "Pat Mahomes,QB,QB,KC,4,8000,99.00%,1.0,1.0,0.0\n"
)
PROJECTIONS = (
    ",Player,Position,Team,Opponent,Salary,% ownership\n"
    '0,Pat Mahomes,QB,KC,@LV,"$8,000",27.5%\n'
    '1,Missing Guy,WR,KC,@LV,"$5,000",3.0%\n'
)


def _folder(tmp_path, with_projections=True):
    (tmp_path / "DK-main-slate-contest-standings-week3.csv").write_text(STANDINGS)
    (tmp_path / "DKSalaries-week3.csv").write_text(SALARY)
    (tmp_path / "DK-Players.csv").write_text(PLAYERS)
    if with_projections:
        (tmp_path / "ownership-projections-week3.csv").write_text(PROJECTIONS)
    return tmp_path


def test_resolves_lineups_and_strips_dst_names(tmp_path):
    week = load_week(_folder(tmp_path), 3)
    assert len(week.lineups) == 1  # rank 2 has an unknown player and is skipped
    lineup = week.lineups[0]
    assert lineup.rank == 1 and lineup.points == 200.5
    assert [slot for slot, _ in lineup.players][:3] == ["DST", "FLEX", "QB"]
    dst = next(p for slot, p in lineup.players if slot == "DST")
    assert dst.name == "Chiefs" and dst.dk_id == "8"
    flex = next(p for slot, p in lineup.players if slot == "FLEX")
    assert flex.position == "WR"  # a FLEX keeps his real position
    assert any("Nobody Known" in issue for issue in week.issues)


def test_opponent_comes_from_game_info(tmp_path):
    week = load_week(_folder(tmp_path), 3)
    assert week.pool["Pat Mahomes"].opponent == "LV"
    assert week.pool["Rb Two"].opponent == "KC"


def test_main_slate_pool_excludes_other_teams(tmp_path):
    week = load_week(_folder(tmp_path), 3)
    assert week.main_slate_teams == {"KC", "LV"}
    assert "Off Slate" not in week.pool and "Pat Mahomes" in week.pool


def test_ownership_comes_from_the_contest_table_not_dk_players(tmp_path):
    week = load_week(_folder(tmp_path), 3)
    mahomes = week.pool["Pat Mahomes"]
    # The standings table says 30.00%; DK-Players' all-games 12.5%/99% values
    # are ignored.
    assert mahomes.actual_pct == 30.0
    assert mahomes.projected_pct == 27.5
    assert mahomes.fpts == 25.0
    # Absent from the contest table = undrafted = 0.0, with FPTS falling back
    # to DK-Players for the same week.
    rb_one = week.pool["Rb One"]
    assert rb_one.actual_pct == 0.0 and rb_one.fpts == 14.0
    assert week.pool["Rb Two"].actual_pct == 0.0 and week.pool["Rb Two"].projected_pct is None
    assert any("Missing Guy" in issue for issue in week.issues)


def test_missing_projections_is_flagged_not_fatal(tmp_path):
    week = load_week(_folder(tmp_path, with_projections=False), 3)
    assert week.has_projections is False
    assert "no ownership projections for this week" in week.issues


def test_missing_standings_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_week(tmp_path, 3)


def test_parse_projections_applies_aliases():
    assert parse_projections(PROJECTIONS, {"Pat Mahomes": "Patrick Mahomes"}) == {
        "Patrick Mahomes": 27.5,
        "Missing Guy": 3.0,
    }
