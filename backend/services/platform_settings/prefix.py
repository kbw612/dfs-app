"""
Maps a platform name to the short filename prefix used for this week's
shared salary/ownership files (backend/repositories/dk_salary/
salary_snapshot_repo.py, backend/repositories/ownership/
projections_repo.py) -- e.g. "DraftKings" -> "dk", giving
"dk_salary_week3.csv". Centralized here so both repos agree on the same
mapping, and so adding a real second platform later (e.g. FanDuel -> "fd")
is a one-line addition to _PLATFORM_PREFIXES rather than something
duplicated in each file-path builder.

Also maps a contest name to the filename slug woven into every
contest-scoped filename -- e.g. "All Games" -> "all_games", used by
backend/repositories/dk_salary/salary_snapshot_repo.py,
backend/repositories/contest_results/contest_standings_repo.py, and
backend/repositories/player_selection/player_selection_repo.py. Every
contest gets a slug, including "Classic Main" -- unlike the platform
prefix (where only DraftKings has a real file format today), every
contest-scoped file always includes its contest's slug in the name, so
switching the Contest chip always means a fully independent file rather
than one contest quietly reusing an unsegmented "default" filename. Same
"centralize the mapping" reasoning as the platform prefixes above.
"""

from __future__ import annotations

_PLATFORM_PREFIXES: dict[str, str] = {
    "DraftKings": "dk",
}

_CONTEST_SLUGS: dict[str, str] = {
    "Classic Main": "classic_main",
    "All Games": "all_games",
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


def contest_slug(contest: str) -> str:
    """Raises ValueError for any contest that isn't a real option, same
    convention as platform_file_prefix."""
    slug = _CONTEST_SLUGS.get(contest)
    if slug is None:
        raise ValueError(f"Unsupported contest: {contest!r} -- choose one of {list(_CONTEST_SLUGS)}.")
    return slug
