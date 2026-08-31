"""
GET /position-blocks?season=&week=&position=&block_size=&same_game_only=&team=&game=&platform=&salary_bucket=
(mounted at /api/ownership/position-blocks -- see
backend/api/ownership/__init__.py). Reads the shared DK salary snapshot
(see backend/api/dk_salary/import_csv.py) for salary/team/opponent, the
same one Player Pool uses -- not the Ownership tab's own snapshot, so this
view no longer requires the Ownership tab to have loaded anything for the
week. If the Ownership tab *does* have a snapshot for the same (season,
week), its ownership_pct values get opportunistically merged in by player
name for display (see dk_salary.ownership_enrich.enrich_with_ownership_pct)
-- purely for the ownership% shown per player, not required. See
backend/services/ownership/position_blocks.py's docstring for the "player
blocks by position" concept this implements (ported from the uploaded
contest_player_stacks_v2.py script) and what did/didn't carry over from
it.

Filtering order: position (required) -> team (optional, keep only these
teams) -> game (optional, keep only these matchups) -> same_game_only
decides how the *remaining* pool gets grouped into combinations (see
compute_position_blocks()) -> salary_bucket (optional, keep only blocks
whose total_salary falls in one of the selected percent-of-cap buckets --
see SALARY_BUCKETS) is applied last, as a post-filter on the generated
blocks rather than the player pool, since it doesn't reduce the
combinatorics that MAX_BLOCKS_SAFETY_CAP guards against. `team`/`game`/
`salary_bucket` are all repeatable query params (?team=KC&team=BUF),
matching the frontend's multi-select chip filters elsewhere in this view.

`platform` (default "DraftKings") does double duty: it picks which
SALARY_CAPS entry salary_bucket's percentages resolve against (it does
*not* change block-size rules or anything else -- see SALARY_CAPS's
docstring for why), and it picks which platform's raw salary file gets
loaded (see backend/services/platform_settings/prefix.py) -- a platform
without an uploaded file for this (season, week) still 404s, same as
today, just per-platform now instead of always "the" DK file.

The `games` list in the response is every distinct matchup among this
position's players *before* the team/game filters are applied, not after
-- it's what populates the game-filter chips themselves, so it shouldn't
shrink as soon as you've already filtered down to one game. Players
narrowed out by Settings' Player Selection grid (see
backend/services/player_selection/engine.py's filter_selected_players)
are dropped before any of this -- they never appear in a block, and never
populate the game-filter chips either. RB/WR/TE are the only positions
this endpoint deals with, so the "DST is never filtered" carve-out in
filter_selected_players never actually comes up here, but the same shared
filter is used for consistency with Player Pool.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.ownership.snapshot_repo import (
    find_latest_snapshot as find_latest_ownership_snapshot,
    load_snapshot as load_ownership_snapshot,
)
from backend.repositories.player_selection.player_selection_repo import load_overrides
from backend.schemas.ownership.ownership import PositionBlock
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct
from backend.services.ownership.position_blocks import (
    SALARY_CAPS,
    compute_position_blocks,
    filter_blocks_by_salary_buckets,
    game_key,
    game_label,
    validate_block_size,
)
from backend.services.player_selection.engine import filter_selected_players

router = APIRouter()


class GameOption(BaseModel):
    key: str
    label: str


class PositionBlocksResult(BaseModel):
    blocks: list[PositionBlock]
    games: list[GameOption]


@router.get("/position-blocks", response_model=PositionBlocksResult)
def position_blocks_endpoint(
    season: int,
    week: int,
    position: str,
    block_size: int,
    same_game_only: bool = False,
    team: list[str] = Query(default=[]),
    game: list[str] = Query(default=[]),
    platform: str = "DraftKings",
    salary_bucket: list[str] = Query(default=[]),
) -> PositionBlocksResult:
    try:
        validate_block_size(position, block_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cap = SALARY_CAPS.get(platform)
    if cap is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown platform '{platform}' -- choose one of {list(SALARY_CAPS)}.",
        )

    try:
        csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if csv_text is None:
        raise HTTPException(
            status_code=404,
            detail=f"No DK salary file uploaded yet for season {season} week {week} -- upload this week's DK salary export first.",
        )
    salary_snapshot, _messages = parse_dk_salary_csv(csv_text, season, week)

    ownership_snapshot_path = find_latest_ownership_snapshot(settings.ownership_snapshots_dir, season=season, week=week)
    ownership_players = load_ownership_snapshot(ownership_snapshot_path).players if ownership_snapshot_path else None
    players = enrich_with_ownership_pct(salary_snapshot.players, ownership_players)

    overrides = load_overrides(settings.nfl_data_dir, season, week, platform)
    players = filter_selected_players(players, overrides)

    position_players = [p for p in players if p.position == position]

    game_options_by_key = {}
    for player in position_players:
        key = game_key(player)
        if key not in game_options_by_key:
            game_options_by_key[key] = GameOption(key="-".join(sorted(key)), label=game_label(key))
    games = sorted(game_options_by_key.values(), key=lambda g: g.label)

    pool = position_players
    if team:
        team_set = set(team)
        pool = [p for p in pool if p.team in team_set]
    if game:
        selected_game_keys = {frozenset(g.split("-")) for g in game}
        pool = [p for p in pool if game_key(p) in selected_game_keys]

    try:
        blocks = compute_position_blocks(pool, block_size, same_game_only)
        blocks = filter_blocks_by_salary_buckets(blocks, salary_bucket, cap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PositionBlocksResult(blocks=blocks, games=games)
