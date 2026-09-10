"""
Persists My Player Pool's explicit per-player membership flags (see
backend/schemas/my_player_pool/my_player_pool.py) -- one small JSON file
per (season, week, platform, contest), same data/nfl/{season}/ layout as
Player Selection's own override file (see backend/repositories/
player_selection/player_selection_repo.py), but its own separate file/
module -- the two features are independent by design, not just
independently editable.

Contest-scoped for the same reason Player Selection is -- the shortlist
is built from a particular contest's own Salary File's player universe
(see backend/api/my_player_pool/latest.py), so a player added under
Classic Main has no bearing on All Games' own shortlist.

Only players explicitly toggled at least once appear here at all; a
player who's never been added is simply absent, treated as "not in the
pool" (see backend/services/my_player_pool/engine.py's
in_my_player_pool) -- there's no computed default the way Player
Selection has.

Shape on disk (data/nfl/{season}/{prefix}_my_player_pool_{contest_slug}_
week{week}.json):

    {"Josh Allen": true, "CeeDee Lamb": true, "Some Backup RB": false}
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.platform_settings.prefix import contest_slug, platform_file_prefix


def _path(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> Path:
    prefix = platform_file_prefix(platform)
    slug = contest_slug(contest)
    return nfl_data_dir / str(season) / f"{prefix}_my_player_pool_{slug}_week{week}.json"


def load_membership(nfl_data_dir: Path, season: int, week: int, platform: str, contest: str) -> dict[str, bool]:
    """Empty dict if nothing's ever been added yet for this (season, week,
    platform, contest) -- every player defaults to "not in the pool" (see
    engine.py's in_my_player_pool)."""
    path = _path(nfl_data_dir, season, week, platform, contest)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_membership(
    nfl_data_dir: Path, season: int, week: int, platform: str, contest: str, player: str, in_pool: bool
) -> None:
    path = _path(nfl_data_dir, season, week, platform, contest)
    path.parent.mkdir(parents=True, exist_ok=True)
    membership = load_membership(nfl_data_dir, season, week, platform, contest)
    membership[player] = in_pool
    path.write_text(json.dumps(membership, indent=2), encoding="utf-8")
