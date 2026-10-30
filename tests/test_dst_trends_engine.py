from backend.services.dst_trends.dst_trends_engine import build_dst_trend_leaderboards


def _line(team, opponent, week, sacks, def_int=0, fumble_recoveries=0):
    return {
        "team": team,
        "opponent": opponent,
        "sacks": sacks,
        "def_int": def_int,
        "fumble_recoveries": fumble_recoveries,
    }


def test_build_dst_trend_leaderboards_empty_when_week_is_1():
    # week 1 has no prior week to review -- through_week would be 0.
    result = build_dst_trend_leaderboards({}, season=2026, week=1, window_weeks=5)
    assert result.through_week == 0
    assert result.forcing == []
    assert result.allowing == []


def test_build_dst_trend_leaderboards_forcing_attributes_sacks_to_own_team():
    lines = {
        ("Chargers", 1): _line("LAC", "DEN", 1, sacks=4),
        ("Chargers", 2): _line("LAC", "KC", 2, sacks=2),
    }
    result = build_dst_trend_leaderboards(lines, season=2026, week=3, window_weeks=5)
    lac = next(r for r in result.forcing if r.team == "LAC")
    assert lac.games == 2
    assert lac.sacks == 6
    assert lac.sacks_per_game == 3.0


def test_build_dst_trend_leaderboards_allowing_attributes_sacks_to_opponent():
    lines = {
        ("Chargers", 1): _line("LAC", "DEN", 1, sacks=4),
        ("Broncos", 1): _line("DEN", "LAC", 1, sacks=1),
    }
    result = build_dst_trend_leaderboards(lines, season=2026, week=2, window_weeks=5)
    # DEN's own offense gave up 4 sacks to LAC's DST that week -- shows up
    # in `allowing` under DEN, NOT under LAC (LAC's own 1-sack allowance
    # from Denver's DST shows up under LAC instead).
    den_allowing = next(r for r in result.allowing if r.team == "DEN")
    assert den_allowing.sacks == 4
    lac_allowing = next(r for r in result.allowing if r.team == "LAC")
    assert lac_allowing.sacks == 1


def test_build_dst_trend_leaderboards_takeaways_sums_def_int_and_fumble_recoveries():
    lines = {("Chargers", 1): _line("LAC", "DEN", 1, sacks=0, def_int=2, fumble_recoveries=1)}
    result = build_dst_trend_leaderboards(lines, season=2026, week=2, window_weeks=5)
    lac = next(r for r in result.forcing if r.team == "LAC")
    assert lac.takeaways == 3
    assert lac.takeaways_per_game == 3.0


def test_build_dst_trend_leaderboards_respects_window_weeks():
    lines = {
        ("Chargers", 1): _line("LAC", "DEN", 1, sacks=10),  # outside a 2-week window ending at week 3
        ("Chargers", 2): _line("LAC", "KC", 2, sacks=2),
        ("Chargers", 3): _line("LAC", "LV", 3, sacks=4),
    }
    result = build_dst_trend_leaderboards(lines, season=2026, week=4, window_weeks=2)
    lac = next(r for r in result.forcing if r.team == "LAC")
    assert lac.games == 2
    assert lac.sacks == 6  # weeks 2+3 only, week 1's 10 excluded


def test_build_dst_trend_leaderboards_window_clamped_to_week_1():
    lines = {("Chargers", 1): _line("LAC", "DEN", 1, sacks=3)}
    result = build_dst_trend_leaderboards(lines, season=2026, week=2, window_weeks=5)
    # through_week=1, window_weeks=5 would ask for weeks -3..1 -- clamped to just week 1.
    lac = next(r for r in result.forcing if r.team == "LAC")
    assert lac.games == 1
    assert lac.sacks == 3


def test_build_dst_trend_leaderboards_sorted_by_sacks_per_game_descending():
    lines = {
        ("Chargers", 1): _line("LAC", "DEN", 1, sacks=1),
        ("Chiefs", 1): _line("KC", "LV", 1, sacks=5),
    }
    result = build_dst_trend_leaderboards(lines, season=2026, week=2, window_weeks=5)
    assert [r.team for r in result.forcing] == ["KC", "LAC"]


def test_build_dst_trend_leaderboards_ignores_rows_with_no_team_or_opponent():
    lines = {("Some Team", 1): {"team": "", "opponent": "", "sacks": 5, "def_int": 0, "fumble_recoveries": 0}}
    result = build_dst_trend_leaderboards(lines, season=2026, week=2, window_weeks=5)
    assert result.forcing == []
    assert result.allowing == []


def test_contest_teams_narrows_rows_but_not_their_numbers():
    lines = {
        ("A", 1): {"team": "AAA", "opponent": "BBB", "sacks": 3, "def_int": 1, "fumble_recoveries": 0},
        ("B", 1): {"team": "BBB", "opponent": "AAA", "sacks": 1, "def_int": 0, "fumble_recoveries": 0},
        ("C", 1): {"team": "CCC", "opponent": "DDD", "sacks": 5, "def_int": 0, "fumble_recoveries": 0},
    }
    full = build_dst_trend_leaderboards(lines, season=2026, week=2, window_weeks=5)
    narrowed = build_dst_trend_leaderboards(lines, season=2026, week=2, window_weeks=5, contest_teams={"AAA", "BBB"})
    assert {r.team for r in full.forcing} == {"AAA", "BBB", "CCC"}
    assert [r.team for r in narrowed.forcing] == ["AAA", "BBB"]
    assert [r.team for r in narrowed.allowing] == ["BBB", "AAA"]
    assert next(r for r in narrowed.forcing if r.team == "AAA") == next(r for r in full.forcing if r.team == "AAA")


def test_endpoint_adds_dst_salary_per_team(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    j = TestClient(app).get("/api/dst-trends", params=dict(season=2026, week=8, window_weeks=5, scope="contest")).json()
    assert j["forcing"] and all(r["salary"] is None or r["salary"] >= 2000 for r in j["forcing"])
