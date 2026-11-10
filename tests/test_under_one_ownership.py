from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.ownership.parsing import UNDER_ONE_PCT, is_under_one_placeholder, parse_ownership_pct
from backend.services.ownership.under_one import hide_below_cutoff


def P(name, pos, own, team="AAA", opp="BBB", salary=5000):
    return OwnershipPlayer(player=name, position=pos, team=team, opponent=opp, salary=salary, ownership_pct=own)


def test_placeholder_parses_and_is_recognised():
    assert parse_ownership_pct("0.001%") == UNDER_ONE_PCT
    assert is_under_one_placeholder(parse_ownership_pct("0.001%"))
    assert not is_under_one_placeholder(0.25) and not is_under_one_placeholder(1.0) and not is_under_one_placeholder(None)


def test_filter_hides_only_rb_wr_te_below_the_cutoff_and_never_qb_or_dst():
    players = [
        P("Placeholder RB", "RB", UNDER_ONE_PCT),
        P("Real decimal WR", "WR", 0.25),
        P("Exactly one TE", "TE", 1.0),
        P("Low QB", "QB", 0.58),
        P("Low DST", "DST", 0.74),
        P("Unknown WR", "WR", None),
        P("Normal RB", "RB", 12.0),
    ]
    kept = [p.player for p in hide_below_cutoff(players, 1.0)]
    assert kept == ["Exactly one TE", "Low QB", "Low DST", "Unknown WR", "Normal RB"]
    assert len(hide_below_cutoff(players, 0)) == len(players)  # cutoff 0 shows everyone
    assert "Exactly one TE" not in [p.player for p in hide_below_cutoff(players, 2.0)]


CSV = """Player,Team,Position,Opponent,Salary,% ownership
Chalk RB,AAA,RB,BBB,"$7,000",25.00%
Deep RB,AAA,RB,BBB,"$4,000",0.001%
Deep WR,BBB,WR,AAA,"$3,000",0.5%
Low QB,BBB,QB,AAA,"$5,000",0.58%
Low DST,AAA,DST,BBB,"$2,500",0.74%
"""


def _client(tmp_path, monkeypatch):
    from backend.repositories.ownership.projections_repo import save_projections_csv

    monkeypatch.setattr(settings, "nfl_data_dir", tmp_path)
    save_projections_csv(tmp_path, 2026, 3, "DraftKings", CSV)
    return TestClient(app)


def test_ownership_summary_players_and_ownership_pivots_hide_by_default(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    q = dict(season=2026, week=3, platform="DraftKings")
    names = lambda j: {p["player"] for p in j["players"]}
    assert names(c.get("/api/ownership/projections", params=q).json()) == {"Chalk RB", "Low QB", "Low DST"}
    assert names(c.get("/api/ownership/projections", params={**q, "hide_below": 0}).json()) == {"Chalk RB", "Deep RB", "Deep WR", "Low QB", "Low DST"}
    assert names(c.get("/api/ownership/latest", params=q).json()) == {"Chalk RB", "Low QB", "Low DST"}
    assert "Deep RB" in names(c.get("/api/ownership/latest", params={**q, "hide_below": 0}).json())


def test_leverage_pivots_hides_below_cutoff_in_search_names(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    q = dict(season=2026, week=3)
    assert "Deep RB" not in c.get("/api/leverage-pivots", params=q).json()["search_names"]
    assert "Deep RB" in c.get("/api/leverage-pivots", params={**q, "hide_below": 0}).json()["search_names"]


def test_lineup_analyzer_counts_the_placeholder_as_point_one_percent():
    from backend.schemas.ownership.ownership import OwnershipSnapshot
    from backend.services.lineup_analyzer.live_slate import build_live_week

    salary_csv = (
        "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"
        "RB,Deep RB (1),Deep RB,1,RB/FLEX,4000,AAA@BBB 01:00PM ET,AAA,5\n"
        "RB,Chalk RB (2),Chalk RB,2,RB/FLEX,7000,AAA@BBB 01:00PM ET,AAA,15\n"
    )
    ownership = [P("Deep RB", "RB", UNDER_ONE_PCT), P("Chalk RB", "RB", 25.0)]
    week, _ = build_live_week(salary_csv, ownership, 2026, 3)
    assert week.pool["Deep RB"].actual_pct == 0.1 and week.pool["Chalk RB"].actual_pct == 25.0
