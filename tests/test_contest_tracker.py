import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.schemas.contest_tracker.contest_tracker import TrackerContest, TrackerEntry, TrackerFile
from backend.services.contest_tracker.summary import summarize


def _entry(c, week, cost, won):
    return TrackerEntry(contest_id=c, week=week, cost=cost, won=won)


def test_summary_matches_the_sheet_and_skips_unplayed_weeks():
    data = TrackerFile(
        season=2026,
        contests=[TrackerContest(id="m", name="mini-Max (.50)"), TrackerContest(id="s", name="Singleback")],
        entries=[
            _entry("m", 1, 50, 49.5), _entry("m", 2, 50, 0), _entry("m", 3, 50, 55), _entry("m", 4, 50, 88),
            _entry("m", 6, 55, 37.5), _entry("m", 7, 50, 65.5), _entry("s", 5, 5, 1.5),
        ],
    )
    r = summarize(data)
    m, s = r.contests
    assert (m.cost, m.won, m.roi_pct, m.played) == (305, 295.5, -3.11, 6)
    assert (s.cost, s.won, s.roi_pct, s.played) == (5, 1.5, -70.0, 1)
    assert r.weeks_elapsed == 7
    assert r.week_net[5] == -3.5  # only Singleback played week 5
    assert 5 in r.week_net and r.net == pytest.approx(-13.0)
    assert r.total_roi_pct == pytest.approx((297 - 310) / 310 * 100, abs=0.01)


def test_empty_contest_has_no_roi():
    r = summarize(TrackerFile(season=2026, contests=[TrackerContest(id="a", name="A")]))
    assert r.contests[0].roi_pct is None and r.total_roi_pct is None and r.weeks_elapsed == 0


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "nfl_data_dir", tmp_path, raising=False)
    return TestClient(app)


def test_api_flow_add_edit_skip_rename_delete(client):
    q = {"season": 2026}
    cid = client.post("/api/contest-tracker/contests", params=q, json={"name": "Daily Dollar (SE)"}).json()["contests"][0]["id"]
    assert client.post("/api/contest-tracker/contests", params=q, json={"name": "daily dollar (se)"}).status_code == 400

    body = {"contest_id": cid, "week": 1, "cost": 1, "won": 4, "top_finishes": [{"place": 497, "payout": 4}]}
    r = client.put("/api/contest-tracker/entries", params=q, json=body).json()
    assert r["contests"][0]["roi_pct"] == 300.0
    body["won"] = 0
    r = client.put("/api/contest-tracker/entries", params=q, json=body).json()  # replaces, not duplicates
    assert r["contests"][0]["played"] == 1 and r["contests"][0]["roi_pct"] == -100.0

    assert client.put("/api/contest-tracker/entries", params=q, json={**body, "cost": 0}).status_code == 422
    assert client.put("/api/contest-tracker/entries", params=q, json={**body, "contest_id": "nope"}).status_code == 404

    r = client.delete("/api/contest-tracker/entries", params={**q, "contest_id": cid, "week": 1}).json()
    assert r["contests"][0]["played"] == 0
    assert client.patch(f"/api/contest-tracker/contests/{cid}", params=q, json={"name": "DD"}).json()["contests"][0]["name"] == "DD"
    assert client.get("/api/contest-tracker", params=q).json()["contests"][0]["name"] == "DD"
    assert client.delete(f"/api/contest-tracker/contests/{cid}", params=q).json()["contests"] == []
    assert client.get("/api/contest-tracker", params={"season": 2027}).json()["contests"] == []
