from backend.services.game_logs_summary.qb_passing import build_qb_passing
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


def _line(team, opponent, yds, att=35):
    return {"team": team, "opponent": opponent, "pass_yds": yds, "pass_att": att}


def _lines():
    return {
        ("Justin Herbert", 1): _line("LAC", "DEN", 305, 40),
        ("Justin Herbert", 2): _line("LAC", "KC", 270),
        ("Patrick Mahomes", 1): _line("KC", "MIA", 250, 38),
        ("Patrick Mahomes", 2): _line("KC", "LAC", 320, 41),
        ("Bo Nix", 1): _line("DEN", "LAC", 280, 36),
        ("Bo Nix", 2): _line("DEN", "MIA", 200, 30),
        ("Tua Tagovailoa", 1): _line("MIA", "KC", 150, 28),
        ("Tua Tagovailoa", 2): _line("MIA", "DEN", 290, 37),
        ("Backup QB", 1): _line("LAC", "DEN", 100, 3),
    }


def _build(**kwargs):
    kwargs.setdefault("window_weeks", 5)
    return build_qb_passing(_lines(), parse_schedule_csv(SCHEDULE_CSV), 3, **kwargs)


def _row(result, name):
    return next(r for r in result.rows if r.name == name)


def test_none_when_no_lines_in_window():
    assert build_qb_passing({}, parse_schedule_csv(SCHEDULE_CSV), 3, 5) is None


def test_slate_totals_split_300_from_265_299():
    result = _build()
    assert result.qb_games_300 == 2  # Herbert 305, Mahomes 320
    assert result.qb_games_265_299 == 3  # Herbert 270, Nix 280, Tua 290
    assert result.defense_allowed_300 == 2  # DEN (Herbert), LAC (Mahomes)
    assert result.defense_allowed_265_299 == 3  # KC (Herbert), LAC (Nix), DEN (Tua)
    assert (result.first_week, result.through_week) == (1, 2)


def test_per_qb_buckets_do_not_overlap_and_carry_home_away():
    herbert = _row(_build(), "Justin Herbert")
    assert [(g.week, g.opponent, g.is_home, g.pass_yds) for g in herbert.over_300] == [(1, "DEN", False, 305)]
    assert [(g.week, g.opponent, g.is_home, g.pass_yds) for g in herbert.range_265_299] == [(2, "KC", True, 270)]
    assert herbert.opponent == "DEN"


def test_opponent_allowed_lists_265_plus_oldest_first_with_defense_home_away():
    herbert = _row(_build(), "Justin Herbert")
    allowed = [(a.week, a.passer, a.passer_team, a.defense_is_home, a.pass_yds) for a in herbert.opponent_allowed]
    # DEN was home in week 1 and away in week 2.
    assert allowed == [(1, "Justin Herbert", "LAC", True, 305), (2, "Tua Tagovailoa", "MIA", False, 290)]


def test_contest_teams_scopes_qbs_and_defenses():
    result = _build(contest_teams={"LAC", "DEN"})
    assert result.qb_games_300 == 1  # Mahomes (KC) is off the slate
    assert result.qb_games_265_299 == 2  # Herbert 270, Nix 280; Tua is off
    assert all(r.team in {"LAC", "DEN"} for r in result.rows)


def test_window_limits_weeks():
    result = _build(window_weeks=1)
    assert (result.first_week, result.through_week) == (2, 2)
    assert result.qb_games_300 == 1  # only Mahomes 320


def test_backup_with_no_265_game_gets_no_row():
    names = {r.name for r in _build().rows}
    assert "Backup QB" not in names
    assert "Justin Herbert" in names


def test_best_setups_need_two_allowed_and_sort_by_count():
    result = _build()
    setups = {s.name: s.allowed_count for s in result.best_setups}
    assert setups["Justin Herbert"] == 2  # DEN allowed Herbert 305 and Tua 290
    assert setups["Bo Nix"] == 2  # LAC allowed Mahomes 320 and Nix 280
    assert "Patrick Mahomes" not in setups  # MIA allowed none
    assert all(s.allowed_count >= 2 for s in result.best_setups)
