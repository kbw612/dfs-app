"""
Step 4 of the pipeline (Section 2 of the design doc): save_snapshot(), plus
the read-side helpers the UI/diff endpoints need: list_snapshots() (the
picker in the frontend needs to enumerate every snapshot on disk),
find_snapshot_by_id() / load_snapshot() (fetch one by its id), and
find_latest_snapshot() (still handy as "the most recent one").

Local-disk storage for Phase 1. Kept behind this one small module
deliberately -- when Phase 2 (Section 2) swaps in Google Cloud Storage,
this is the only file that should need to change; scraper.py, enrich.py,
and diff.py don't know or care where snapshots end up.

Every run is kept indefinitely (full history retained), one file per run,
named from the snapshot's own scraped_at timestamp. That filename doubles
as the snapshot's id everywhere else in the app (API URLs, the frontend's
picker) -- "depth_chart_2026-08-07_0800.json" <-> id "2026-08-07_0800".
"""

from __future__ import annotations

from pathlib import Path

from backend.schemas.depth_charts.snapshot import Snapshot

_FILENAME_PREFIX = "depth_chart_"


def _filename_from_scraped_at(scraped_at: str) -> str:
    # "2026-08-07T08:00:00-04:00" -> "2026-08-07_0800"
    date_part, time_part = scraped_at.split("T")
    time_compact = time_part[:5].replace(":", "")
    return f"{_FILENAME_PREFIX}{date_part}_{time_compact}.json"


def snapshot_id_from_path(file_path: Path) -> str:
    """"depth_chart_2026-08-07_0800.json" -> "2026-08-07_0800"."""
    return file_path.stem.removeprefix(_FILENAME_PREFIX)


def save_snapshot(snapshot: Snapshot, snapshots_dir: Path) -> Path:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    file_path = snapshots_dir / _filename_from_scraped_at(snapshot.scraped_at)
    file_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    return file_path


def load_snapshot(file_path: Path) -> Snapshot:
    return Snapshot.model_validate_json(file_path.read_text(encoding="utf-8"))


def list_snapshots(snapshots_dir: Path) -> list[Path]:
    """Every saved snapshot, oldest first -- filenames sort chronologically
    since they're built from scraped_at, so a plain sort is enough, no need
    to read every file's contents just to order them.
    """
    if not snapshots_dir.exists():
        return []
    return sorted(snapshots_dir.glob(f"{_FILENAME_PREFIX}*.json"))


def find_latest_snapshot(snapshots_dir: Path) -> Path | None:
    """Most recent already-saved snapshot, or None on the very first run
    (empty/missing directory)."""
    snapshots = list_snapshots(snapshots_dir)
    return snapshots[-1] if snapshots else None


def find_snapshot_by_id(snapshots_dir: Path, snapshot_id: str) -> Path | None:
    """snapshot_id is the filename minus the "depth_chart_" prefix and
    ".json" suffix, e.g. "2026-08-07_0800" -- see snapshot_id_from_path().
    """
    candidate = snapshots_dir / f"{_FILENAME_PREFIX}{snapshot_id}.json"
    return candidate if candidate.exists() else None
