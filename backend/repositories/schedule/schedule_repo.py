"""
Persists the full-season Team/Week/Opponent/GameLocation schedule CSV
(backend/services/schedule/schedule_loader.py) that backs the Game Logs
tab's Opponent/GameLoc columns and its Game filter -- one file per
season, uploaded once via Settings (unlike almost everything else in this
app, the source file already covers every week at once, so there's no
per-week dimension here). Not tied to a platform or contest either -- an
NFL schedule is the same regardless of which DK contest you're building
for. Same "always overwritten, re-parsed fresh on every read" convention
as every other snapshot repo in this app.
"""

from __future__ import annotations

from pathlib import Path


def _path(nfl_data_dir: Path, season: int) -> Path:
    return nfl_data_dir / str(season) / "schedule.csv"


def schedule_csv_path(nfl_data_dir: Path, season: int) -> Path:
    return _path(nfl_data_dir, season)


def save_schedule_csv(nfl_data_dir: Path, season: int, csv_text: str) -> Path:
    file_path = _path(nfl_data_dir, season)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(csv_text, encoding="utf-8")
    return file_path


def load_schedule_csv(nfl_data_dir: Path, season: int) -> str | None:
    file_path = _path(nfl_data_dir, season)
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")
