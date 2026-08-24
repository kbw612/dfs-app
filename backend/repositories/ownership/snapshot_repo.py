"""
Ownership snapshot persistence -- same shape as
depth_charts/snapshot_repo.py (save/load/list/find_latest/find_by_id),
local-disk storage for Phase 1. Kept behind this one module for the same
reason: swapping local storage for cloud storage later only touches this
file.

Filenames are built from (season, week, scraped_at) rather than
scraped_at alone, since -- unlike depth charts -- ownership snapshots are
meaningfully scoped to one week's slate and multiple scrapes of the *same*
week (as ownership shifts through the day) need to sort and diff sensibly
against each other, not just against whatever was scraped most recently
overall. "ownership_2025_week15_2026-08-07_0800.json" <-> id
"2025_week15_2026-08-07_0800".
"""

from __future__ import annotations

from pathlib import Path

from backend.schemas.ownership.ownership import OwnershipSnapshot

_FILENAME_PREFIX = "ownership_"


def _filename_from_snapshot(snapshot: OwnershipSnapshot) -> str:
    # "2026-08-07T08:00:00-04:00" -> "2026-08-07_0800"
    date_part, time_part = snapshot.scraped_at.split("T")
    time_compact = time_part[:5].replace(":", "")
    return f"{_FILENAME_PREFIX}{snapshot.season}_week{snapshot.week}_{date_part}_{time_compact}.json"


def snapshot_id_from_path(file_path: Path) -> str:
    """"ownership_2025_week15_2026-08-07_0800.json" -> "2025_week15_2026-08-07_0800"."""
    return file_path.stem.removeprefix(_FILENAME_PREFIX)


def save_snapshot(snapshot: OwnershipSnapshot, snapshots_dir: Path) -> Path:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    file_path = snapshots_dir / _filename_from_snapshot(snapshot)
    file_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    return file_path


def load_snapshot(file_path: Path) -> OwnershipSnapshot:
    return OwnershipSnapshot.model_validate_json(file_path.read_text(encoding="utf-8"))


def list_snapshots(snapshots_dir: Path, season: int | None = None, week: int | None = None) -> list[Path]:
    """Every saved snapshot, oldest first (filenames sort chronologically
    within the same season/week since they end in date_time). Optionally
    narrowed to one (season, week) -- the common case, since almost every
    caller cares about "this week's ownership history," not the full
    cross-season pile."""
    if not snapshots_dir.exists():
        return []

    pattern = f"{_FILENAME_PREFIX}*.json"
    if season is not None and week is not None:
        pattern = f"{_FILENAME_PREFIX}{season}_week{week}_*.json"

    return sorted(snapshots_dir.glob(pattern))


def find_latest_snapshot(snapshots_dir: Path, season: int | None = None, week: int | None = None) -> Path | None:
    """Most recent already-saved snapshot (optionally scoped to one
    season/week), or None if there isn't one yet."""
    snapshots = list_snapshots(snapshots_dir, season=season, week=week)
    return snapshots[-1] if snapshots else None


def find_snapshot_by_id(snapshots_dir: Path, snapshot_id: str) -> Path | None:
    """snapshot_id is the filename minus the "ownership_" prefix and
    ".json" suffix, e.g. "2025_week15_2026-08-07_0800" -- see
    snapshot_id_from_path()."""
    candidate = snapshots_dir / f"{_FILENAME_PREFIX}{snapshot_id}.json"
    return candidate if candidate.exists() else None
