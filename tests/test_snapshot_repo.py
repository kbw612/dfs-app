from pathlib import Path

from backend.repositories.depth_charts.snapshot_repo import (
    find_latest_snapshot,
    find_snapshot_by_id,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    snapshot_id_from_path,
)
from backend.schemas.depth_charts.snapshot import Snapshot


def make_snapshot(scraped_at: str) -> Snapshot:
    return Snapshot(scraped_at=scraped_at, source_url="https://example.com", teams=[])


def test_save_then_load_round_trips(tmp_path: Path):
    snapshot = make_snapshot("2026-08-07T08:00:00-04:00")
    file_path = save_snapshot(snapshot, tmp_path)

    loaded = load_snapshot(file_path)
    assert loaded == snapshot


def test_find_latest_snapshot_returns_none_when_dir_missing(tmp_path: Path):
    missing_dir = tmp_path / "does-not-exist"
    assert find_latest_snapshot(missing_dir) is None


def test_find_latest_snapshot_returns_none_when_dir_empty(tmp_path: Path):
    assert find_latest_snapshot(tmp_path) is None


def test_find_latest_snapshot_picks_newest_by_timestamp(tmp_path: Path):
    save_snapshot(make_snapshot("2026-08-07T08:00:00-04:00"), tmp_path)
    save_snapshot(make_snapshot("2026-08-14T08:00:00-04:00"), tmp_path)
    save_snapshot(make_snapshot("2026-08-10T08:00:00-04:00"), tmp_path)

    latest = find_latest_snapshot(tmp_path)
    assert latest is not None
    assert "2026-08-14" in latest.name


def test_snapshot_id_from_path_strips_prefix_and_suffix():
    assert snapshot_id_from_path(Path("depth_chart_2026-08-07_0800.json")) == "2026-08-07_0800"


def test_list_snapshots_returns_empty_list_when_dir_missing(tmp_path: Path):
    assert list_snapshots(tmp_path / "does-not-exist") == []


def test_list_snapshots_sorted_oldest_first(tmp_path: Path):
    save_snapshot(make_snapshot("2026-08-14T08:00:00-04:00"), tmp_path)
    save_snapshot(make_snapshot("2026-08-07T08:00:00-04:00"), tmp_path)
    save_snapshot(make_snapshot("2026-08-10T08:00:00-04:00"), tmp_path)

    paths = list_snapshots(tmp_path)
    ids = [snapshot_id_from_path(p) for p in paths]
    assert ids == ["2026-08-07_0800", "2026-08-10_0800", "2026-08-14_0800"]


def test_find_snapshot_by_id_returns_matching_path(tmp_path: Path):
    save_snapshot(make_snapshot("2026-08-07T08:00:00-04:00"), tmp_path)

    found = find_snapshot_by_id(tmp_path, "2026-08-07_0800")
    assert found is not None
    assert found.exists()


def test_find_snapshot_by_id_returns_none_when_missing(tmp_path: Path):
    assert find_snapshot_by_id(tmp_path, "1999-01-01_0000") is None
