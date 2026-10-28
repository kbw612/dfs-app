from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.schemas.player_groups.player_groups import GroupPlayer, PlayerGroup
from backend.services.player_groups.groups_file import merge_groups, parse_groups_csv, write_groups_csv
from backend.services.player_groups.pool import filter_pool, parse_pool, validate_groups

SAMPLE = (
    "Group,GroupName,Id,Name,AnchorPlayer,MinGroup,MaxGroup,Pct\n"
    "0,Det,44664465,Jahmyr Gibbs,false,2,4,1\n"
    "0,Det,44664393,Jared Goff,true,2,4,1\n"
    "1,Min,44664727,Justin Jefferson,false,1,9,0.80\n"
)

SALARY = (
    "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame,Status\n"
    "RB,Jahmyr Gibbs (44664465),Jahmyr Gibbs,44664465,RB/FLEX,9500,MIN@DET 11/01/2026 01:00PM ET,DET,30.3,\n"
    "QB,Jared Goff (44664393),Jared Goff,44664393,QB,6600,MIN@DET 11/01/2026 01:00PM ET,DET,23.8,\n"
    "WR,Justin Jefferson (44664727),Justin Jefferson,44664727,WR/FLEX,7100,MIN@DET 11/01/2026 01:00PM ET,MIN,20,\n"
    "WR,Puka Nacua (1),Puka Nacua,1,WR/FLEX,8400,LAR@LV 11/01/2026 04:05PM ET,LAR,20,\n"
)


def test_roundtrip_is_byte_for_byte():
    assert write_groups_csv(parse_groups_csv(SAMPLE)) == SAMPLE


def test_real_blink_sample_roundtrips_if_present():
    path = Path(__file__).parent / "fixtures" / "blink_groups_sample.csv"
    if path.exists():
        text = path.read_text()
        assert write_groups_csv(parse_groups_csv(text)) == text


def test_parse_values_and_anchor():
    g = parse_groups_csv(SAMPLE)
    assert [x.name for x in g] == ["Det", "Min"]
    assert (g[0].pct, g[0].min, g[0].max) == (100.0, 2, 4) and g[1].pct == 80.0
    assert [p.anchor for p in g[0].players] == [False, True]


def test_bad_header_rejected():
    with pytest.raises(ValueError):
        parse_groups_csv("a,b\n1,2\n")


def test_merge_replaces_same_name_keeps_others_appends_new():
    old = [PlayerGroup(name="Det", players=[GroupPlayer(id="1", name="A")]), PlayerGroup(name="Keep")]
    new = [PlayerGroup(name="det", players=[GroupPlayer(id="2", name="B")]), PlayerGroup(name="Added")]
    m = merge_groups(old, new, replace_all=False)
    assert [g.name for g in m] == ["det", "Keep", "Added"] and m[0].players[0].id == "2"
    assert [g.name for g in merge_groups(old, new, replace_all=True)] == ["det", "Added"]


def test_pool_games_and_filter_sorted_by_salary():
    players, games = parse_pool(SALARY)
    assert [g.label for g in games] == ["LAR @ LV", "MIN @ DET"]
    det = filter_pool(players, ["DET-MIN"], "ALL", "", "")
    assert [p.name for p in det] == ["Jahmyr Gibbs", "Justin Jefferson", "Jared Goff"]
    assert [p.name for p in filter_pool(players, [], "WR", "", "")] == ["Puka Nacua", "Justin Jefferson"]
    assert [p.name for p in filter_pool(players, [], "ALL", "DET", "goff")] == ["Jared Goff"]


def test_validation_messages():
    bad = [PlayerGroup(name="A", min=5, max=2), PlayerGroup(name="a"), PlayerGroup(name="B", players=[GroupPlayer(id="1", name="x"), GroupPlayer(id="1", name="x")])]
    assert len(validate_groups(bad)) == 3


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend.repositories.dk_salary.salary_snapshot_repo import _path

    monkeypatch.setattr(settings, "nfl_data_dir", tmp_path, raising=False)
    p = _path(tmp_path, 2026, 8, "DraftKings", "Classic Main")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(SALARY)
    return TestClient(app)


def test_api_import_save_summary_export(client):
    q = {"season": 2026, "week": 8}
    r = client.post("/api/player-groups/import", params=q, files={"file": ("g.csv", SAMPLE)}).json()
    det = r["groups"][0]
    assert det["player_count"] == 2 and det["salary_total"] == 16100 and det["missing_ids"] == []

    groups = [g for g in r["groups"]]
    groups.reverse()  # drag-reorder: Min first
    saved = client.put("/api/player-groups", params=q, json={"groups": groups}).json()
    assert [g["name"] for g in saved["groups"]] == ["Min", "Det"]
    assert [g["name"] for g in client.get("/api/player-groups", params=q).json()["groups"]] == ["Min", "Det"]
    csv_text = client.post("/api/player-groups/export", params={"week": 8}, json={"groups": groups}).json()["csv"]
    assert csv_text.splitlines()[1].startswith("0,Min,") and "1,Det," in csv_text

    bad = client.put("/api/player-groups", params=q, json={"groups": [{"name": "X", "min": 5, "max": 1}]})
    assert bad.status_code == 400
    assert client.post("/api/player-groups/import", params=q, files={"file": ("g.csv", "nope\n")}).status_code == 400
    pool = client.get("/api/player-groups/pool", params={**q, "game": "DET-MIN", "position": "WR"}).json()
    assert [p["name"] for p in pool["players"]] == ["Justin Jefferson"] and len(pool["games"]) == 2


def test_filter_pool_by_my_player_pool_combines_with_position():
    players, _ = parse_pool(SALARY)
    names = {"Jahmyr Gibbs", "Justin Jefferson"}
    assert [p.name for p in filter_pool(players, [], "RB", "", "", names)] == ["Jahmyr Gibbs"]
    assert [p.name for p in filter_pool(players, [], "ALL", "", "", names)] == ["Jahmyr Gibbs", "Justin Jefferson"]
    assert filter_pool(players, [], "ALL", "", "", set()) == []


def test_api_pool_my_pool_filter(client):
    from backend.repositories.my_player_pool.my_player_pool_repo import save_membership

    q = {"season": 2026, "week": 8}
    save_membership(settings.nfl_data_dir, 2026, 8, "DraftKings", "Classic Main", "Jahmyr Gibbs", True)
    save_membership(settings.nfl_data_dir, 2026, 8, "DraftKings", "Classic Main", "Justin Jefferson", False)
    r = client.get("/api/player-groups/pool", params={**q, "my_pool": True, "position": "RB"}).json()
    assert [p["name"] for p in r["players"]] == ["Jahmyr Gibbs"] and r["my_pool_count"] == 1
    assert len(client.get("/api/player-groups/pool", params=q).json()["players"]) == 4


def test_hide_min_salary_drops_players_at_their_position_floor():
    text = SALARY + "WR,Min Guy (2),Min Guy,2,WR/FLEX,3000,MIN@DET 11/01/2026 01:00PM ET,MIN,1,\nRB,Min Back (3),Min Back,3,RB/FLEX,4000,MIN@DET 11/01/2026 01:00PM ET,DET,1,\n"
    players, _ = parse_pool(text)
    assert {p.name for p in filter_pool(players, ["DET-MIN"], "ALL", "", "")} >= {"Min Guy", "Min Back"}
    shown = {p.name for p in filter_pool(players, ["DET-MIN"], "ALL", "", "", None, True)}
    assert "Min Guy" not in shown and "Min Back" not in shown and "Jahmyr Gibbs" in shown
    # the floor is contest-wide, so a game with only one WR keeps that WR if he's above the floor
    assert "Puka Nacua" in {p.name for p in filter_pool(players, ["LAR-LV"], "ALL", "", "", None, True)}
