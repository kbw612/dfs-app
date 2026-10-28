from backend.services.exposure.exposure import LineupPlayer as P
from backend.services.exposure.exposure import build_exposure, make_view


def _lineup(flex_name, flex_pos, wr="W1"):
    return [
        P("QB", "Q", "QB", "A", 6000), P("RB", "R1", "RB", "A", 7000), P("RB", "R2", "RB", "B", 5000),
        P("WR", wr, "WR", "A", 6000), P("WR", "W2", "WR", "B", 5000), P("WR", "W3", "WR", "C", 4000),
        P("TE", "T", "TE", "C", 3500), P("FLEX", flex_name, flex_pos, "D", 4500), P("DST", "D1", "DST", "E", 2500),
    ]


def test_counts_flex_split_and_field_difference():
    lineups = [_lineup("F1", "RB"), _lineup("F2", "WR"), _lineup("F3", "WR", wr="W9"), _lineup("F4", "TE")]
    r = build_exposure("x", "X", lineups, field_pct={"Q": 50.0, "F2": 10.0}, pts={"Q": 20.0})
    flex = {f.position: (f.count, f.pct) for f in r.flex}
    assert flex == {"RB": (1, 25.0), "WR": (2, 50.0), "TE": (1, 25.0)}
    by = {p.name: p for p in r.players}
    assert (by["Q"].count, by["Q"].exposure_pct, by["Q"].diff, by["Q"].pts) == (4, 100.0, 50.0, 20.0)
    assert (by["F2"].exposure_pct, by["F2"].diff) == (25.0, 15.0)
    assert by["W9"].count == 1 and by["R1"].field_pct is None and by["R1"].diff is None


def test_compare_pct_defaults_to_zero_when_pool_lacks_player():
    r = build_exposure("x", "X", [_lineup("F1", "RB")], compare_pct={"Q": 40.0})
    by = {p.name: p for p in r.players}
    assert by["Q"].compare_pct == 40.0 and by["R1"].compare_pct == 0.0


def test_view_filters_sorts_and_falls_back_to_first_scope():
    a = build_exposure("a", "A", [_lineup("F1", "RB"), _lineup("F2", "WR")], field_pct={"F1": 5.0, "F2": 40.0})
    b = build_exposure("b", "B", [_lineup("F1", "RB")])
    v = make_view([a, b], "nope", "WR", "salary", "Field %")
    assert v.selected == "a" and [p.position for p in v.players] == ["WR"] * len(v.players)
    assert [p.salary for p in v.players] == sorted([p.salary for p in v.players], reverse=True)
    v = make_view([a, b], "a", "ALL", "diff", "Field %")
    assert v.players[0].name == "F1"  # 50 - 5 = +45 beats F2's 50 - 40 = +10
    assert [s.key for s in v.scopes] == ["a", "b"] and not v.has_pts
