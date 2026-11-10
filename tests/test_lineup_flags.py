from backend.schemas.lineup_analyzer.flags import FlagSettings
from backend.services.lineup_analyzer.flags import FlagContext, flag_lineup, flag_pool, summarize
from backend.services.lineup_analyzer.history_loader import HistoricalPlayer


def P(name, pos, team, opp, salary, own=5.0):
    return HistoricalPlayer(name, pos, team, opp, salary, f"id-{name}", own, own, None)


POOL = {
    p.name: p
    for p in [
        P("QB1", "QB", "ATL", "TB", 5500),
        P("RB1", "RB", "ATL", "TB", 7000),
        P("RB2", "RB", "KC", "DEN", 6000),
        P("WR1", "WR", "ATL", "TB", 7000),
        P("WR2", "WR", "DET", "GB", 6000),
        P("WR3", "WR", "LV", "LAC", 5000),
        P("TE1", "TE", "SF", "SEA", 4000),
        P("FLEXRB", "RB", "NYJ", "MIA", 5000),
        P("DST1", "DST", "KC", "DEN", 3000),
        # extras
        P("TBWR", "WR", "TB", "ATL", 4000),
        P("PUNT1", "WR", "CIN", "TEN", 3000),
        P("PUNT2", "WR", "CIN", "TEN", 3200),
        P("PUNT3", "TE", "CIN", "TEN", 3500),
        P("RB3", "RB", "ATL", "TB", 6000),
        P("DSTTB", "DST", "TB", "ATL", 2500),
    ]
}
ID_TO_NAME = {p.dk_id: n for n, p in POOL.items()}
CLEAN = ["QB1", "RB1", "RB2", "WR1", "WR2", "WR3", "TE1", "FLEXRB", "DST1"]


def cells(names):
    return [(n, POOL[n].dk_id if n in POOL else "") for n in names]


def codes(names, ctx=None, copies=1):
    ctx = ctx or FlagContext(POOL, ID_TO_NAME)
    return {f.code for f in flag_lineup(cells(names), copies, ctx).flags}


def with_slot(slot_index, name):
    out = list(CLEAN)
    out[slot_index] = name
    return out


def test_a_clean_lineup_has_no_flags():
    assert codes(CLEAN) == set()


def test_errors_over_cap_not_on_slate_duplicate_and_invalid_slot():
    pool = {**POOL, "RB1": P("RB1", "RB", "ATL", "TB", 20000)}
    assert "over_cap" in codes(CLEAN, FlagContext(pool, ID_TO_NAME))
    assert codes(with_slot(2, "Ghost Player")) == {"not_on_slate"}
    assert codes(with_slot(2, "RB1")) == {"duplicate_player"}  # RB1 twice
    assert "invalid_slot" in codes(with_slot(7, "DSTTB"))  # a DST can't play FLEX
    assert "invalid_slot" not in codes(with_slot(7, "TBWR"))  # a WR in FLEX is fine


def test_dst_conflict_injury_and_duplicate_warnings():
    lineup = with_slot(8, "DSTTB")  # TB DST faces ATL; QB1, RB1, WR1 are ATL
    assert "dst_conflict" in codes(lineup)
    flag = next(f for f in flag_lineup(cells(lineup), 1, FlagContext(POOL, ID_TO_NAME)).flags if f.code == "dst_conflict")
    assert "QB1" in flag.text and "RB1" in flag.text and "WR1" in flag.text and "DSTTB" in flag.text
    ctx = FlagContext(POOL, ID_TO_NAME, injury={"wr1": "D", "rb2": "O"})
    assert "injury" in codes(CLEAN, ctx)
    assert "duplicate_lineup" in codes(CLEAN, copies=3)


def test_notes_no_qb_stack_low_total_weather_underdog_punts():
    assert "no_qb_stack" not in codes(CLEAN)  # RB1 and WR1 are ATL like QB1
    assert "no_qb_stack" in codes(["QB1", "RB2", "FLEXRB", "WR2", "WR3", "PUNT1", "TE1", "TBWR", "DST1"])
    ctx = FlagContext(POOL, ID_TO_NAME, lines={"ATL": (18.0, 20.0, 38.0), "TB": (20.0, 18.0, 38.0)}, bad_weather_teams={"DET"})
    got = flag_lineup(cells(CLEAN), 1, ctx).flags
    text = next(f.text for f in got if f.code == "low_total_weather")
    assert "ATL vs TB (total 38" in text and "DET vs GB (bad weather)" in text
    dog_ctx = FlagContext(POOL, ID_TO_NAME, lines={"KC": (14.0, 28.0, 42.0), "ATL": (24.0, 20.0, 44.0)})
    dogs = next(f.text for f in flag_lineup(cells(CLEAN), 1, dog_ctx).flags if f.code == "big_underdog")
    assert "RB2 (KC, 14.0-point underdog)" in dogs and "DST1" in dogs
    punts = ["QB1", "RB1", "RB2", "PUNT1", "PUNT2", "WR3", "PUNT3", "FLEXRB", "DST1"]
    assert "too_many_punts" in codes(punts)
    assert "too_many_punts" not in codes(CLEAN)


def test_same_team_rbs_starter_risk_and_thresholds_are_editable():
    twin = ["QB1", "RB1", "RB3", "WR2", "WR3", "WR1", "TE1", "FLEXRB", "DST1"]
    assert "same_team_rbs" in codes(twin)
    ctx = FlagContext(POOL, ID_TO_NAME, depth={"rb2": 3, "wr3": 2, "te1": 2})
    risky = next(f.text for f in flag_lineup(cells(CLEAN), 1, ctx).flags if f.code == "starter_risk")
    assert "RB2 (RB3)" in risky and "TE1 (TE2)" in risky and "WR3" not in risky
    ctx = FlagContext(POOL, ID_TO_NAME, lines={"ATL": (18.0, 20.0, 38.0)}, settings=FlagSettings(low_total=30))
    assert "low_total_weather" not in {f.code for f in flag_lineup(cells(CLEAN), 1, ctx).flags}


def test_pool_level_flags_near_duplicates_and_ownership_extremes():
    near = with_slot(5, "TBWR")  # differs from CLEAN by one player
    far = ["QB1", "RB1", "RB3", "WR1", "TBWR", "PUNT1", "TE1", "PUNT2", "DSTTB"]
    pool = {**POOL, "RB1": P("RB1", "RB", "ATL", "TB", 7000, own=40.0), "PUNT1": P("PUNT1", "WR", "CIN", "TEN", 3000, own=0.5),
            "PUNT2": P("PUNT2", "WR", "CIN", "TEN", 3200, own=0.5)}
    ctx = FlagContext(pool, ID_TO_NAME, settings=FlagSettings(own_slice_pct=25))
    result = flag_pool([cells(CLEAN), cells(near), cells(far)], [1, 1, 1], ctx)
    by_index = {r.index: {f.code for f in r.flags} for r in result}
    assert "near_duplicate" in by_index[0] and "near_duplicate" in by_index[1] and "near_duplicate" not in by_index[2]
    assert "ownership_extreme" in by_index[2] and "ownership_extreme" not in by_index[0]  # only the low-owned lineup
    summary = {s.code: s.count for s in summarize(result)}
    assert summary["near_duplicate"] == 2 and summary["over_cap"] == 0


def test_upload_remembers_dropped_duplicate_copies(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.config import settings
    from backend.main import app
    from backend.repositories.lineup_analyzer.pool_repo import load_pool

    monkeypatch.setattr(settings, "nfl_data_dir", tmp_path)
    header = "QB,RB,RB,WR,WR,WR,TE,FLEX,DST"
    row = ",".join(f"{n} ({i})" for i, n in enumerate(["Q", "R1", "R2", "W1", "W2", "W3", "T", "F", "D"]))
    other = row.replace("Q (0)", "Q2 (9)")
    client = TestClient(app)
    files = [("files", ("a.csv", f"{header}\n{row}\n{other}\n{row}\n", "text/csv")), ("files", ("b.csv", f"{header}\n{row}\n", "text/csv"))]
    r = client.post("/api/lineup-analyzer/upload", params={"season": 2026, "week": 1}, files=files)
    assert r.status_code == 200 and r.json()["lineup_count"] == 2
    pool = load_pool(tmp_path, 2026, 1, "DraftKings", "Classic Main")
    assert pool["copies"] == [3, 1]
