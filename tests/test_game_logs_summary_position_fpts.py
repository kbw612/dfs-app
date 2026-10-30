from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.services.game_logs_summary.position_fpts import build_position_fpts
from backend.services.schedule.schedule_loader import parse_schedule_csv

SCHEDULE = parse_schedule_csv(
    "Team,Week,Opponent,GameLocation\n"
    "LAC,1,DEN,Away\nDEN,1,LAC,Home\n"
    "LAC,2,KC,Home\nKC,2,LAC,Away\nDEN,2,MIA,Away\nMIA,2,DEN,Home\n"
    "LAC,3,DEN,Home\nDEN,3,LAC,Away\nKC,3,MIA,Away\nMIA,3,KC,Home\n"
)


def _row(name, team, week, salary, fpts, position="QB"):
    return DkPlayerRow(
        name=name, position=position, roster_position=position, team=team, week=week, salary=salary,
        pct_drafted=0.0, fpts=fpts, non_td_fpts=fpts, td_fpts=0.0,
    )


ROWS = [
    _row("Herbert", "LAC", 1, 6000, 28.0),  # Elite (27+); allowed by DEN
    _row("Herbert", "LAC", 2, 6000, 22.0),  # Strong (22-26.9); allowed by KC
    _row("Nix", "DEN", 1, 5800, 24.5),  # Strong; allowed by LAC
    _row("Nix", "DEN", 2, 5800, 10.0),  # below both bands
    _row("Mahomes", "KC", 2, 7000, 27.0),  # exactly 27 -> Elite; allowed by LAC
    _row("Wr Guy", "KC", 2, 5000, 30.0, position="WR"),  # other position: ignored for QB
]


def _build(**kw):
    return build_position_fpts(ROWS, SCHEDULE, 3, 5, position="QB", **kw)


def _row_for(summary, name):
    return next(r for g in summary.groups for r in g.rows if r.name == name)


def test_bands_counts_and_labels():
    s = _build()
    assert (s.elite_label, s.strong_label, s.opponent_label) == ("27+", "22-26.9", "Opp D")
    assert s.weeks_label == "Weeks 1-2"
    assert (s.player_games_elite, s.player_games_strong) == (2, 2)
    assert (s.allowed_elite, s.allowed_strong) == (2, 2)
    herbert = _row_for(s, "Herbert")
    assert (herbert.elite.count, herbert.strong.count) == (1, 1)
    assert [l.text for l in herbert.elite.lines] == ["Week 1: @ DEN 28.0 ($6.0K)"]
    assert [l.text for l in herbert.strong.lines] == ["Week 2: vs KC 22.0 ($6.0K)"]


def test_rows_group_by_this_weeks_opponent_with_allowed_lines_once():
    s = _build()
    by_opp = {g.opponent: g for g in s.groups}
    # Week 3: LAC faces DEN and DEN faces LAC; KC faces MIA.
    assert set(by_opp) == {"DEN", "LAC", "MIA"}
    den = by_opp["DEN"]  # DEN allowed Herbert's 28.0 in week 1
    assert den.row_count == 1 and den.allowed_elite.count == 1 and den.allowed_strong.count == 0
    assert [l.text for l in den.allowed_elite.lines] == ["Week 1: Herbert vs LAC 28.0 ($6.0K)"]  # DEN was at home, so "vs"
    lac = by_opp["LAC"]  # LAC allowed Nix 24.5 (week 1) and Mahomes 27.0 (week 2)
    assert (lac.allowed_elite.count, lac.allowed_strong.count, lac.allowed_total) == (1, 1, 2)
    assert s.best_setups == ["Nix vs LAC (2 allowed 22+)"]
    assert [g.opponent for g in s.groups][0] == "LAC"  # most allowed first


def test_team_filter_narrows_rows_not_the_allowed_lists():
    s = _build(team_filter={"DEN"})
    assert [r.name for g in s.groups for r in g.rows] == ["Nix"]
    assert s.row_count == 1
    assert {g.opponent: g.allowed_total for g in s.groups}["LAC"] == 2


def test_dst_uses_opposing_offense_label_and_own_bands():
    rows = [
        _row("Chargers", "LAC", 1, 3000, 9.0, position="DST"),  # Strong for DST starts at 8
        _row("Broncos", "DEN", 1, 3000, 14.0, position="DST"),  # Elite
        _row("Chiefs", "KC", 2, 3000, 7.9, position="DST"),  # below Strong
    ]
    s = build_position_fpts(rows, SCHEDULE, 3, 5, position="DST")
    assert (s.opponent_label, s.elite_label, s.strong_label) == ("Opp offense", "14+", "8-13.9")
    assert (s.player_games_elite, s.player_games_strong) == (1, 1)
    assert next(r for g in s.groups for r in g.rows if r.name == "Chargers").strong.count == 1


def test_no_rows_for_position_returns_none_and_contest_scope_applies():
    assert build_position_fpts(ROWS, SCHEDULE, 3, 5, position="TE") is None
    s = build_position_fpts(ROWS, SCHEDULE, 3, 5, contest_teams={"LAC", "DEN"}, position="QB")
    assert {r.name for g in s.groups for r in g.rows} == {"Herbert", "Nix"}


def test_qb_detail_shows_attempts_and_only_scored_touchdowns():
    stats = {
        ("Herbert", 1): {"pass_att": 38, "pass_td": 3, "rush_td": 0},
        ("Herbert", 2): {"pass_att": 31},  # no TD keys at all
        ("Nix", 1): {"pass_att": 35, "pass_td": 0, "rush_td": 1},
        ("Mahomes", 2): {"pass_td": 2, "rush_td": 1},  # attempts missing
    }
    s = build_position_fpts(ROWS, SCHEDULE, 3, 5, position="QB", stat_lines=stats)
    assert _row_for(s, "Herbert").elite.lines[0].details == ["38 att · 3 pass TD"]
    assert _row_for(s, "Herbert").strong.lines[0].details == ["31 att"]
    assert _row_for(s, "Nix").strong.lines[0].details == ["35 att · 1 rush TD"]
    assert _row_for(s, "Mahomes").elite.lines[0].details == ["2 pass TD · 1 rush TD"]
    # the same detail follows the game into the opponent's allowed list
    den = next(g for g in s.groups if g.opponent == "DEN")
    assert den.allowed_elite.lines[0].details == ["38 att · 3 pass TD"]


RB_ROWS = [
    _row("Back A", "LAC", 1, 8000, 26.0, position="RB"),  # Elite (23+)
    _row("Back B", "DEN", 2, 7000, 17.0, position="RB"),  # Strong (16-22.9)
]


def test_rb_detail_has_volume_line_then_production_line():
    stats = {
        ("Back A", 1): {"rush_att": 19, "receptions": 5, "targets": 6, "rush_yards": 92, "receiving_yards": 61, "rush_td": 1, "rec_td": 1},
        ("Back B", 2): {"rush_att": 15, "receptions": 5, "targets": 6, "rush_yards": 64, "receiving_yards": 47, "rush_td": 0, "rec_td": 0},
    }
    s = build_position_fpts(RB_ROWS, SCHEDULE, 3, 5, position="RB", stat_lines=stats)
    a = next(r for g in s.groups for r in g.rows if r.name == "Back A")
    assert a.elite.lines[0].details == ["19 car · 5 rec / 6 tgt · 25 opp", "92 rush yds · 61 rec yds · 1 rush TD · 1 rec TD"]
    b = next(r for g in s.groups for r in g.rows if r.name == "Back B")
    assert b.strong.lines[0].details == ["15 car · 5 rec / 6 tgt · 21 opp", "64 rush yds · 47 rec yds"]  # no TD parts when none scored
    # allowed side carries the same lines
    den = next(g for g in s.groups if g.opponent == "DEN")
    assert den.allowed_elite.lines[0].details[0] == "19 car · 5 rec / 6 tgt · 25 opp"


def test_wr_detail_receiving_line_then_rushing_line_only_if_carried():
    rows = [_row("Wr A", "LAC", 1, 6800, 31.0, position="WR"), _row("Wr B", "DEN", 2, 5400, 17.0, position="WR")]
    stats = {
        ("Wr A", 1): {"targets": 11, "receptions": 9, "receiving_yards": 142, "rec_td": 2, "rush_att": 2, "rush_yards": 18, "rush_td": 1},
        ("Wr B", 2): {"targets": 8, "receptions": 6, "receiving_yards": 92, "rec_td": 0, "rush_att": 0, "rush_yards": 0, "rush_td": 0},
    }
    s = build_position_fpts(rows, SCHEDULE, 3, 5, position="WR", stat_lines=stats)
    a = next(r for g in s.groups for r in g.rows if r.name == "Wr A")
    assert a.elite.lines[0].details == ["11 tgt · 9 rec · 142 rec yds · 2 rec TD", "2 car · 18 rush yds · 1 rush TD"]
    b = next(r for g in s.groups for r in g.rows if r.name == "Wr B")
    assert b.strong.lines[0].details == ["8 tgt · 6 rec · 92 rec yds"]


def test_no_stat_line_or_other_position_has_no_details():
    s = build_position_fpts(ROWS, SCHEDULE, 3, 5, position="QB")
    assert _row_for(s, "Herbert").elite.lines[0].details == []
    from backend.services.game_logs_summary.position_fpts import _details
    assert _details("K", {("Kicker", 2): {"targets": 5}}, "Kicker", 2) == []


def test_dst_detail_sacks_always_other_plays_only_when_they_happened():
    from backend.services.game_logs_summary.position_fpts import _details
    line = {"sacks": 4, "def_int": 0, "fumble_recoveries": 2, "safeties": 0, "def_td": 1, "ret_td": 0}
    assert _details("DST", {("Bengals", 1): line}, "Bengals", 1) == ["4 sck · 2 fum rec · 1 def TD"]
    assert _details("DST", {("Bengals", 1): {"sacks": 0}}, "Bengals", 1) == ["0 sck"]


def test_te_detail_matches_wr_lines():
    from backend.services.game_logs_summary.position_fpts import _details
    line = {"targets": 10, "receptions": 8, "receiving_yards": 96, "rec_td": 2, "rush_att": 1, "rush_yards": 3, "rush_td": 1}
    assert _details("TE", {("Te A", 1): line}, "Te A", 1) == ["10 tgt · 8 rec · 96 rec yds · 2 rec TD", "1 car · 3 rush yds · 1 rush TD"]


def test_attach_salaries_fills_flat_and_grouped_rows():
    from types import SimpleNamespace as NS
    from backend.services.game_logs_summary.shared import attach_salaries, salary_lookup

    lookup = salary_lookup([NS(player="Justin Herbert", team="LAC", salary=6200)])
    s = build_position_fpts(ROWS, SCHEDULE, 3, 5, position="QB")
    attach_salaries([s, None], lookup)
    assert _row_for(s, "Herbert").salary is None  # not in the salary list
    flat = NS(rows=[NS(name="Justin Herbert", team="LAC", salary=None)])
    attach_salaries([flat], lookup)
    assert flat.rows[0].salary == 6200
