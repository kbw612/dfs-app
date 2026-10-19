"""TD columns on the QB passing and RB rushing panels, and the RB receiving
panel (backend/services/game_logs_summary/)."""

from backend.services.game_logs_summary.qb_passing import build_qb_passing
from backend.services.game_logs_summary.rb_receiving import build_rb_receiving
from backend.services.game_logs_summary.rb_rushing import build_rb_rushing
from backend.services.schedule.schedule_loader import parse_schedule_csv

SCHEDULE_CSV = (
    "Team,Week,Opponent,GameLocation\n"
    "LAC,1,DEN,Away\n"
    "DEN,1,LAC,Home\n"
    "KC,1,MIA,Home\n"
    "MIA,1,KC,Away\n"
    "LAC,2,KC,Home\n"
    "KC,2,LAC,Away\n"
    "DEN,2,MIA,Away\n"
    "MIA,2,DEN,Home\n"
    "LAC,3,DEN,Home\n"
    "DEN,3,LAC,Away\n"
    "KC,3,MIA,Away\n"
    "MIA,3,KC,Home\n"
)
SCHEDULE = parse_schedule_csv(SCHEDULE_CSV)


def _row(result, name):
    return next(r for r in result.rows if r.name == name)


# -- QB: 3+ passing TD games --------------------------------------------------


def _qb(team, opp, td, yds=100, att=35):
    return {"team": team, "opponent": opp, "pass_yds": yds, "pass_att": att, "pass_td": td}


def _qb_lines():
    return {
        ("Justin Herbert", 1): _qb("LAC", "DEN", 3),
        ("Justin Herbert", 2): _qb("LAC", "KC", 1),
        ("Patrick Mahomes", 1): _qb("KC", "MIA", 2),
        ("Patrick Mahomes", 2): _qb("KC", "LAC", 4),
        ("Bo Nix", 1): _qb("DEN", "LAC", 3),
        ("Bo Nix", 2): _qb("DEN", "MIA", 0),
        ("Tua Tagovailoa", 1): _qb("MIA", "KC", 0),
        ("Tua Tagovailoa", 2): _qb("MIA", "DEN", 1),
    }


def test_qb_td_totals_count_3_plus_games_only():
    result = build_qb_passing(_qb_lines(), SCHEDULE, 3, 5)
    assert result.qb_games_td3 == 3  # Herbert w1, Mahomes w2, Nix w1
    assert result.defense_allowed_td3 == 3  # DEN once, LAC twice


def test_qb_td_own_and_allowed_lists():
    result = build_qb_passing(_qb_lines(), SCHEDULE, 3, 5)
    herbert = _row(result, "Justin Herbert")
    assert [(g.week, g.opponent, g.pass_td) for g in herbert.td_games] == [(1, "DEN", 3)]
    assert [(g.week, g.passer) for g in herbert.opponent_allowed_td] == [(1, "Justin Herbert")]

    nix = _row(result, "Bo Nix")  # faces LAC in week 3
    assert [(g.week, g.passer, g.passer_team, g.pass_td) for g in nix.opponent_allowed_td] == [
        (1, "Bo Nix", "DEN", 3),
        (2, "Patrick Mahomes", "KC", 4),
    ]
    # LAC was away in week 1 and home in week 2.
    assert [g.defense_is_home for g in nix.opponent_allowed_td] == [False, True]


def test_qb_without_td_or_yardage_signal_gets_no_row():
    result = build_qb_passing(_qb_lines(), SCHEDULE, 3, 5)
    assert "Tua Tagovailoa" not in [r.name for r in result.rows]


# -- RB rushing: 1+ rushing TD games ------------------------------------------


def _rush(team, opp, yds, td):
    return {"team": team, "opponent": opp, "rush_yards": yds, "rush_td": td}


def _rush_lines():
    return {
        ("Austin Ekeler", 1): _rush("LAC", "DEN", 60, 1),
        ("Kimani Vidal", 1): _rush("LAC", "DEN", 45, 0),
        ("Kimani Vidal", 2): _rush("LAC", "KC", 80, 1),
        ("Isiah Pacheco", 1): _rush("KC", "MIA", 110, 0),
        ("Isiah Pacheco", 2): _rush("KC", "LAC", 76, 2),
        ("Javonte Williams", 1): _rush("DEN", "LAC", 30, 1),
        ("Javonte Williams", 2): _rush("DEN", "MIA", 90, 0),
        ("De'Von Achane", 1): _rush("MIA", "KC", 20, 0),
        ("De'Von Achane", 2): _rush("MIA", "DEN", 100, 0),
    }


def test_rb_rushing_td_totals_count_games():
    result = build_rb_rushing(_rush_lines(), SCHEDULE, 3, 5)
    assert result.rb_games_td == 4  # Ekeler w1, Vidal w2, Pacheco w2, Williams w1
    # Team-games: DEN w1, KC w2, LAC w1, LAC w2. Pacheco's 2 TDs is one game.
    assert result.defense_allowed_td == 4


def test_rb_rushing_td_lists():
    result = build_rb_rushing(_rush_lines(), SCHEDULE, 3, 5)
    vidal = _row(result, "Kimani Vidal")  # LAC faces DEN in week 3
    assert [(g.week, g.opponent, g.is_home, g.td) for g in vidal.td_games] == [(2, "KC", True, 1)]
    assert [(g.week, g.team, g.total_td, g.defense_is_home) for g in vidal.opponent_allowed_td] == [
        (1, "LAC", 1, True)
    ]
    assert [(s.name, s.td) for s in vidal.opponent_allowed_td[0].scorers] == [("Austin Ekeler", 1)]

    williams = _row(result, "Javonte Williams")  # DEN faces LAC in week 3
    assert [(g.week, g.team, g.total_td) for g in williams.opponent_allowed_td] == [(1, "DEN", 1), (2, "KC", 2)]
    assert [(s.name, s.td) for s in williams.opponent_allowed_td[1].scorers] == [("Isiah Pacheco", 2)]


# -- RB receiving --------------------------------------------------------------


def _rec(team, opp, yds, td):
    return {"team": team, "opponent": opp, "receiving_yards": yds, "rec_td": td}


def _rec_lines():
    return {
        ("Austin Ekeler", 1): _rec("LAC", "DEN", 30, 0),
        ("Kimani Vidal", 1): _rec("LAC", "DEN", 25, 1),
        ("Kimani Vidal", 2): _rec("LAC", "KC", 60, 0),
        ("Isiah Pacheco", 1): _rec("KC", "MIA", 50, 0),
        ("Isiah Pacheco", 2): _rec("KC", "LAC", 10, 0),
        ("De'Von Achane", 1): _rec("MIA", "KC", 49, 0),
        ("De'Von Achane", 2): _rec("MIA", "DEN", 20, 1),
    }


def test_rb_receiving_none_when_no_lines():
    assert build_rb_receiving({}, SCHEDULE, 3, 5) is None


def test_rb_receiving_totals_use_50_bar_inclusive():
    result = build_rb_receiving(_rec_lines(), SCHEDULE, 3, 5)
    assert result.rb_games_50 == 2  # Vidal 60, Pacheco exactly 50
    # DEN w1 (30+25=55), KC w2 (60), MIA w1 (50); Achane's 49 does not count.
    assert result.defense_allowed_50 == 3
    assert result.rb_games_td == 2
    assert result.defense_allowed_td == 2  # DEN w1 and DEN w2


def test_rb_receiving_rows_combine_backs_and_list_each():
    result = build_rb_receiving(_rec_lines(), SCHEDULE, 3, 5)
    assert sorted(r.name for r in result.rows) == ["Isiah Pacheco", "Kimani Vidal"]

    vidal = _row(result, "Kimani Vidal")  # LAC faces DEN in week 3
    assert [(g.week, g.team, g.total_yds, g.defense_is_home) for g in vidal.opponent_allowed] == [
        (1, "LAC", 55, True)
    ]
    assert [(r.name, r.rec_yds) for r in vidal.opponent_allowed[0].receivers] == [
        ("Austin Ekeler", 30),
        ("Kimani Vidal", 25),
    ]
    assert [(g.week, g.rec_yds) for g in vidal.games_50] == [(2, 60)]
    assert [(g.week, g.td) for g in vidal.td_games] == [(1, 1)]
    assert [(g.week, g.total_td) for g in vidal.opponent_allowed_td] == [(1, 1), (2, 1)]

    pacheco = _row(result, "Isiah Pacheco")  # KC faces MIA in week 3
    assert [(g.week, g.total_yds) for g in pacheco.opponent_allowed] == [(1, 50)]
    assert pacheco.td_games == []


def test_rb_receiving_slate_scoping():
    result = build_rb_receiving(_rec_lines(), SCHEDULE, 3, 5, contest_teams={"LAC", "DEN"})
    assert [r.name for r in result.rows] == ["Kimani Vidal"]
    assert result.rb_games_50 == 1  # Vidal only; Pacheco's KC is off the slate
    assert result.defense_allowed_50 == 1  # DEN w1 only
