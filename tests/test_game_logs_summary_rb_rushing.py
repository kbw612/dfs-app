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


def _line(team, opponent, yds):
    return {"team": team, "opponent": opponent, "rush_yards": yds}


def _lines():
    return {
        # Week 1: LAC backs combine for 105 against DEN (neither back alone hits 75).
        ("Austin Ekeler", 1): _line("LAC", "DEN", 60),
        ("Kimani Vidal", 1): _line("LAC", "DEN", 45),
        ("Kimani Vidal", 2): _line("LAC", "KC", 80),
        ("Isiah Pacheco", 1): _line("KC", "MIA", 110),
        ("Isiah Pacheco", 2): _line("KC", "LAC", 76),
        ("Zero Yards", 2): _line("KC", "LAC", 0),
        ("Javonte Williams", 1): _line("DEN", "LAC", 30),
        ("Javonte Williams", 2): _line("DEN", "MIA", 90),
        ("De'Von Achane", 1): _line("MIA", "KC", 20),
        ("De'Von Achane", 2): _line("MIA", "DEN", 100),
        ("Alec Ingold", 2): _line("MIA", "DEN", 5),  # fullback, counted as a RB
    }


def _build(**kwargs):
    kwargs.setdefault("window_weeks", 5)
    return build_rb_rushing(_lines(), parse_schedule_csv(SCHEDULE_CSV), 3, **kwargs)


def _row(result, name):
    return next(r for r in result.rows if r.name == name)


def test_none_when_no_lines_in_window():
    assert build_rb_rushing({}, parse_schedule_csv(SCHEDULE_CSV), 3, 5) is None


def test_per_rb_totals_split_100_from_75_99():
    result = _build()
    assert result.rb_games_100 == 2  # Pacheco 110, Achane 100
    assert result.rb_games_75_99 == 3  # Vidal 80, Pacheco 76, Williams 90


def test_defense_totals_combine_rbs_per_game():
    result = _build()
    # Combined RB yards by (defense, week): (DEN,1)=105 (LAC backs), (KC,2)=80,
    # (LAC,2)=76, (MIA,1)=110, (LAC,1)=30, (MIA,2)=90, (KC,1)=20,
    # (DEN,2)=105 (Achane 100 + Ingold 5).
    assert result.defense_allowed_100 == 3  # DEN w1, MIA w1, DEN w2
    assert result.defense_allowed_75_99 == 3  # KC w2 (80), LAC w2 (76), MIA w2 (90)


def test_opponent_allowed_lists_each_rusher_and_skips_zero_yards():
    result = _build()
    weeks = {a.week: a for a in _row(result, "Javonte Williams").opponent_allowed}
    # Williams (DEN) faces LAC in week 3: LAC allowed 30 (w1) and 76 (w2).
    assert _row(result, "Javonte Williams").opponent == "LAC"
    assert [a.week for a in _row(result, "Javonte Williams").opponent_allowed] == [2]
    allowed = _row(result, "Javonte Williams").opponent_allowed[0]
    assert allowed.total_yds == 76
    assert [(r.name, r.rush_yds) for r in allowed.rushers] == [("Isiah Pacheco", 76)]  # zero-yard back dropped
    assert weeks[2].defense_is_home is True  # LAC was home in week 2


def test_combined_game_with_no_single_75_back_still_counts_and_lists_both():
    # LAC faces DEN in week 3. DEN allowed 105 to LAC's backs in week 1 (60 + 45),
    # though neither back alone reached 75.
    vidal = _row(_build(), "Kimani Vidal")
    assert vidal.opponent == "DEN"
    game = next(a for a in vidal.opponent_allowed if a.week == 1)
    assert game.total_yds == 105
    assert game.team == "LAC"
    assert [(r.name, r.rush_yds) for r in game.rushers] == [("Austin Ekeler", 60), ("Kimani Vidal", 45)]


def test_row_requires_a_75_plus_game_of_his_own():
    names = {r.name for r in _build().rows}
    assert "Austin Ekeler" not in names  # 60 only
    assert "Alec Ingold" not in names
    assert {"Kimani Vidal", "Isiah Pacheco", "Javonte Williams", "De'Von Achane"} <= names


def test_own_games_carry_home_away_and_never_overlap():
    pacheco = _row(_build(), "Isiah Pacheco")
    assert [(g.week, g.opponent, g.is_home, g.rush_yds) for g in pacheco.over_100] == [(1, "MIA", True, 110)]
    assert [(g.week, g.opponent, g.is_home, g.rush_yds) for g in pacheco.range_75_99] == [(2, "LAC", False, 76)]


def test_contest_teams_and_window():
    scoped = _build(contest_teams={"LAC", "DEN"})
    assert all(r.team in {"LAC", "DEN"} for r in scoped.rows)
    assert scoped.rb_games_100 == 0  # Pacheco/Achane are off the slate
    narrow = _build(window_weeks=1)
    assert (narrow.first_week, narrow.through_week) == (2, 2)


def test_best_setups_need_two_allowed_games():
    result = _build()
    assert all(s.allowed_count >= 2 for s in result.best_setups)
