"""
Maps a platform name to the short filename prefix used for this week's
shared salary/ownership files (backend/repositories/dk_salary/
salary_snapshot_repo.py, backend/repositories/ownership/
projections_repo.py) -- e.g. "DraftKings" -> "dk", giving
"dk_salary_week3.csv". Centralized here so both repos agree on the same
mapping, and so adding a real second platform later (e.g. FanDuel -> "fd")
is a one-line addition to _PLATFORM_PREFIXES rather than something
duplicated in each file-path builder.
"""

from __future__ import annotations

_PLATFORM_PREFIXES: dict[str, str] = {
    "DraftKings": "dk",
}


def platform_file_prefix(platform: str) -> str:
    """Raises ValueError for any platform without a real file format
    behind it yet -- callers should turn that into a 4xx, not a 500 (see
    backend/api/ownership/position_blocks.py's handling of
    validate_block_size for the same pattern)."""
    prefix = _PLATFORM_PREFIXES.get(platform)
    if prefix is None:
        raise ValueError(f"Unsupported platform: {platform!r} -- choose one of {list(_PLATFORM_PREFIXES)}.")
    return prefix
