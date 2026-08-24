from pathlib import Path

from backend.repositories.ownership.snapshot_repo import (
    find_latest_snapshot,
    find_snapshot_by_id,
    list_snapshots,
    load_snapshot,
    save_snapshot,
    snapshot_id_from_path,
)
from backend.schemas.ownership.ownership import OwnershipSnapshot


def make_snapshot(scraped_at: str, season: int = 2025, week: int = 15) -> OwnershipSnapshot:
    return OwnershipSnapshot(
        scraped_at=scraped_at, source_url="https://example.com", season=season, week=week, players=[]
    )


def test_save_then_load_round_trips(tmp_path: Path):
    snapshot = make_snapshot("2026-08-07T08:00:00-04:00")
    file_path = save_snapshot(snapshot, tmp_path)

    loaded = load_snapshot(file_path)
    assert loaded == snapshot


def test_filename_encodes_season_and_week(tmp_path: Path):
    snapshot = make_snapshot("2026-08-07T08:00:00-04:00", season=2025, week=15)
    file_path = save_snapshot(snapshot, tmp_path)
    assert file_path.name == "ownership_2025_week15_2026-08-07_0800.json"


def test_snapshot_id_from_path_strips_prefix_and_suffix():
    id_ = snapshot_id_from_path(Path("ownership_2025_week15_2026-08-07_0800.json"))
    assert id_ == "2025_week15_2026-08-07_0800"


def test_find_latest_snapshot_returns_none_when_empty(tmp_path: Path):
    assert find_latest_snapshot(tmp_path) is None


def test_find_latest_snapshot_scoped_to_season_and_week(tmp_path: Path):
    save_snapshot(make_snapshot("2026-08-07T08:00:00-04:00", week=14), tmp_path)
    save_snapshot(make_snapshot("2026-08-08T08:00:00-04:00", week=15), tmp_path)
    save_snapshot(make_snapshot("2026-08-14T08:00:00-04:00", week=15), tmp_path)

    latest_week_15 = find_latest_snapshot(tmp_path, season=2025, week=15)
    assert latest_week_15 is not None
    assert "2026-08-14" in latest_week_15.name

    latest_overall = find_latest_snapshot(tmp_path)
    assert latest_overall is not None
    assert "2026-08-14" in latest_overall.name


def test_list_snapshots_scoped_excludes_other_weeks(tmp_path: Path):
    save_snapshot(make_snapshot("2026-08-07T08:00:00-04:00", week=14), tmp_path)
    save_snapshot(make_snapshot("2026-08-08T08:00:00-04:00", week=15), tmp_path)

    week_15_only = list_snapshots(tmp_path, season=2025, week=15)
    assert len(week_15_only) == 1
    assert "week15" in week_15_only[0].name


def test_find_snapshot_by_id_returns_matching_path(tmp_path: Path):
    save_snapshot(make_snapshot("2026-08-07T08:00:00-04:00"), tmp_path)
    found = find_snapshot_by_id(tmp_path, "2025_week15_2026-08-07_0800")
    assert found is not None
    assert found.exists()


def test_find_snapshot_by_id_returns_none_when_missing(tmp_path: Path):
    assert find_snapshot_by_id(tmp_path, "2025_week99_1999-01-01_0000") is None
