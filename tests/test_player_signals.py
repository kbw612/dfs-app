from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.vegas_lines.vegas_lines import VegasLineGame, VegasLinesSnapshot, VegasLineValues
from backend.services.player_signals.engine import Context, build_player_signals, load_rows
from backend.services.player_signals.thresholds import DEFAULTS, describe, resolve

RB_HEADER = "NAME,TEAM,POS,WK,OPP,RUSHING_ATT,RUSHING_YDS,RUSHING_TD,RECEIVING_TGTS,RECEIVING_REC,RECEIVING_YDS,RECEIVING_TD,FPTS,TGT_SHARE\n"
DST_HEADER = "NAME,TEAM,POS,WK,OPP,DEF_SCK,DEF_INT,FR,OPP_PTS,FPTS\n"


def rb_csv(lines):
    return RB_HEADER + "\n".join(lines) + "\n"


def player(name, pos="RB", team="AAA", opp="BBB", salary=5000, own=5.0, status=None):
    return OwnershipPlayer(player=name, position=pos, team=team, opponent=opp, salary=salary, ownership_pct=own, status=status)


def ctx(rb_lines, week=6, last_x=5, dst_lines=None, vegas=None, statuses=None, overrides=None):
    rows = {
        "RB": load_rows(rb_csv(rb_lines), "RB"),
        "QB": [], "WR": [], "TE": [],
        "DST": load_rows(DST_HEADER + "\n".join(dst_lines or []) + "\n", "DST"),
    }
    return Context(rows, vegas, statuses or {}, week, last_x, resolve(overrides))


def texts(sp):
    return [(c.polarity, c.text) for c in sp.signals]


def test_defaults_roundtrip_and_override_ignores_unknown_keys():
    assert resolve({"boom_pts": 30, "nope": 1})["boom_pts"] == 30
    assert "nope" not in resolve({"nope": 1})
    assert {t.key for t in describe(resolve(None))} == set(DEFAULTS)


def test_carry_share_streak_and_net_count():
    lines = [f"Back One,AAA,RB,{w},BBB,26,100,1,3,3,20,0,25,16" for w in (3, 4, 5)]
    lines += [f"Back Two,AAA,RB,{w},BBB,6,20,0,1,1,5,0,4,5" for w in (3, 4, 5)]
    c = ctx(lines)
    (sp,) = build_player_signals([player("Back One")], c)
    t = texts(sp)
    assert ("up", "Carry share 81.2% last 3") in t
    assert ("up", "25+ touches in each of last 2") in t
    assert sp.net == sp.up - sp.down and sp.up >= 3
    assert sp.games_used == 3 and sp.pts_last_x == 25.0


def test_committee_back_gets_a_negative_chip_that_reduces_net():
    lines = [f"Split,AAA,RB,{w},BBB,8,30,0,1,1,5,0,6,5" for w in (3, 4, 5)]
    lines += [f"Other,AAA,RB,{w},BBB,16,60,0,1,1,5,0,8,5" for w in (3, 4, 5)]
    (sp,) = build_player_signals([player("Split", salary=5200)], ctx(lines))
    down = [c for c in sp.signals if c.polarity == "down"]
    assert [c.text for c in down] == ["Carry share 33.3% (committee) at $5,200"]
    assert sp.down == 1 and sp.net == sp.up - 1


def test_window_respects_last_x_and_ignores_current_and_future_weeks():
    lines = [f"Back One,AAA,RB,{w},BBB,20,80,0,2,2,10,0,12,10" for w in (1, 2, 3, 4, 5, 6, 7)]
    c = ctx(lines, week=6, last_x=2)
    (sp,) = build_player_signals([player("Back One")], c)
    assert sp.games_used == 2  # weeks 4 and 5 only; weeks 6, 7 are not completed
    assert c.first_week == 4


def test_opponent_history_chip_names_the_players():
    lines = [f"Opp RB {w},CCC,RB,{w},BBB,20,110,1,2,2,10,0,22,10" for w in (1, 2, 3, 4)]
    lines.append("Mine,AAA,RB,5,DDD,10,40,0,1,1,5,0,8,5")
    (sp,) = build_player_signals([player("Mine")], ctx(lines))
    chip = next(c for c in sp.signals if c.text.startswith("Lead RB topped"))
    assert chip.polarity == "up" and "4 of 4" in chip.text and len(chip.detail) == 4
    assert [d.split(" W")[1].split(" ")[0] for d in chip.detail] == ["4", "3", "2", "1"]


def test_game_environment_from_vegas_and_team_scoring():
    vegas = VegasLinesSnapshot(
        season=2026, week=6, initial_scraped_at="x", current_scraped_at="x",
        games=[VegasLineGame(away_name="a", home_name="b", away_team="AAA", home_team="BBB", game_key="BBB-AAA",
                             initial=VegasLineValues(), current=VegasLineValues(over_under=52.0, away_implied_total=28.0, home_implied_total=24.0))],
    )
    c = ctx(["Mine,AAA,RB,5,BBB,10,40,0,1,1,5,0,8,5"], vegas=vegas)
    (sp,) = build_player_signals([player("Mine")], c)
    t = texts(sp)
    assert ("up", "Implied 28") in t and ("up", "Game total 52") in t


def test_low_scoring_offense_is_negative():
    dst = [f"Them,BBB,DST,{w},AAA,2,0,0,10,5" for w in (3, 4, 5)]
    c = ctx(["Mine,AAA,RB,5,BBB,10,40,0,1,1,5,0,8,5"], dst_lines=dst)
    (sp,) = build_player_signals([player("Mine")], c)
    assert ("down", "AAA scores 10/game last 3") in texts(sp)


def test_status_chip_and_out_players_are_left_off():
    rows = ["Mine,AAA,RB,5,BBB,10,40,0,1,1,5,0,8,5"]
    out = build_player_signals([player("Mine", status="Q"), player("Gone", status="IR")], ctx(rows))
    assert [s.player for s in out] == ["Mine"]
    assert ("down", "Listed Q") in texts(out[0])


def test_teammate_out_boosts_backup_back():
    lines = [f"Starter,AAA,RB,{w},BBB,18,70,0,2,2,10,0,12,10" for w in (3, 4, 5)]
    lines += [f"Backup,AAA,RB,{w},BBB,4,15,0,1,1,5,0,3,4" for w in (3, 4, 5)]
    c = ctx(lines, statuses={"starter": "O"})
    sp = next(s for s in build_player_signals([player("Backup")], c))
    assert any(ch.family == "role" and "Starter out" in ch.text for ch in sp.signals)


def test_dst_chips_use_defense_and_opposing_qb():
    dst = [f"Def,AAA,DST,{w},BBB,4,1,1,12,9" for w in (3, 4, 5)]
    dst += [f"Their,BBB,DST,{w},AAA,1,0,0,24,3" for w in (3, 4, 5)]
    c = ctx([], dst_lines=dst)
    (sp,) = build_player_signals([player("Def Team", pos="DST", salary=3000)], c)
    t = [x for _p, x in texts(sp)]
    assert "Sacks 4/game last 3" in t and "Takeaways 2/game last 3" in t


def test_endpoint_min_net_filters_and_thresholds_are_echoed():
    client = TestClient(app)
    r = client.get("/api/player-signals", params={"season": 2026, "week": 9, "min_net": 3})
    if r.status_code == 404:
        return  # no real data in this checkout
    assert r.status_code == 200
    body = r.json()
    assert all(p["net"] >= 3 for p in body["players"])
    assert body["total_players"] >= len(body["players"])
    assert {t["key"] for t in body["thresholds"]} == set(DEFAULTS)
    r2 = client.get("/api/player-signals", params={"season": 2026, "week": 9, "min_net": -5, "thresholds": '{"boom_pts": 99}'})
    assert r2.status_code == 200 and len(r2.json()["players"]) >= len(body["players"])
    assert client.get("/api/player-signals", params={"season": 2026, "week": 9, "thresholds": "[1]"}).status_code == 400
    assert client.get("/api/player-signals", params={"season": 2026, "week": 9, "last_weeks": 0}).status_code == 400


def test_opponent_history_follows_last_x_unless_season_scope():
    lines = [f"Opp RB {w},CCC,RB,{w},BBB,20,110,1,2,2,10,0,22,10" for w in (1, 2)]
    lines += [f"Opp RB {w},CCC,RB,{w},BBB,5,10,0,1,1,5,0,4,10" for w in (3, 4, 5, 6, 7)]
    lines.append("Mine,AAA,RB,7,DDD,10,40,0,1,1,5,0,8,5")
    last = ctx(lines, week=8, last_x=5, overrides={"min_games": 4})
    season = Context(last.rows, None, {}, 8, 5, resolve({"min_games": 4}), "season")
    assert len(last.vs_opp["RB"]["BBB"]) == 5 and len(season.vs_opp["RB"]["BBB"]) == 7
    assert not any(c.text.startswith("Lead RB topped") and c.polarity == "up" for c in build_player_signals([player("Mine")], last)[0].signals)


def test_endpoint_rejects_bad_opponent_scope():
    r = TestClient(app).get("/api/player-signals", params={"season": 2026, "week": 9, "opponent_scope": "x"})
    assert r.status_code == 400


def test_endpoint_falls_back_to_salary_file_without_ownership(tmp_path, monkeypatch):
    from backend.config import settings
    from backend.repositories.dk_salary import salary_snapshot_repo as repo

    season_dir = tmp_path / "2026"
    season_dir.mkdir()
    monkeypatch.setattr(settings, "nfl_data_dir", tmp_path)
    r = TestClient(app).get("/api/player-signals", params={"season": 2026, "week": 9})
    assert r.status_code == 404 and "salary" in r.json()["detail"]
    real = repo.load_salary_csv
    monkeypatch.setattr("backend.api.player_signals.player_signals.load_salary_csv", lambda *a: "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\nRB,A B (1),A B,1,RB/FLEX,5000,AAA@BBB 01:00PM ET,AAA,10\n")
    r = TestClient(app).get("/api/player-signals", params={"season": 2026, "week": 9, "min_net": -9})
    assert r.status_code == 200
    body = r.json()
    assert body["ownership_missing"] is True and body["total_players"] == 1
    assert body["players"][0]["ownership_pct"] is None
    assert real is repo.load_salary_csv
