"""
GET /game-blocks?season=&week=&team=&game=&platform=&salary_bucket=&bringback_size=
(mounted at /api/ownership/game-blocks -- see backend/api/ownership/
__init__.py). Backs Salary Blocks' Onslaught section -- unlike
/position-blocks (single-position combinations), this generates RB/WR/TE
combinations of players drawn from BOTH teams in one game (see
backend/services/ownership/game_blocks.py's compute_game_blocks() for the
exact rules).

Onslaught shows the whole pool of both-teams combinations, narrowable by
either side's own player count via `primary_size` (the majority/"team"
side) and/or `bringback_size` (the minority/"bring back team" side) --
both repeatable query params, same convention as `team`/`game`/
`salary_bucket`. There's no separate `same_game_only` toggle here the way
/position-blocks has one -- every game block is inherently scoped to one
game already, and only one game may be selected at a time (see `game`
below).

Meant to be browsed across the whole slate by default -- no team/game
filter required just to see something. A game whose own roster is too deep
to enumerate (see game_blocks.py's own MAX_GAME_BLOCKS_SAFETY_CAP) is
skipped rather than failing the whole request; its matchup still shows up
in `skipped_games` so the frontend can tell the person it's there and
suggest narrowing by team to bring it back under the cap.

Reuses the exact same player-loading/enrichment pipeline as
/position-blocks (DK salary snapshot + opportunistic ownership_pct merge +
Salary Multiplier's expected_fpts + Player Selection's overrides) --
duplicated here rather than shared, same "small acceptable duplication"
call as elsewhere in this codebase, since factoring it out would mean
inventing a shared return-type/error-code contract for two call sites that
otherwise have no relationship. See position_blocks.py's own docstring for
what each of those enrichment steps does and why.

Filtering order matches /position-blocks: team (optional) -> game
(optional) -> compute_game_blocks() decides the combinations -> salary_bucket
(post-filter on generated blocks) -> primary_size/bringback_size (also
post-filters). `team`/`game`/`salary_bucket`/`primary_size`/
`bringback_size` are all repeatable query params, matching the frontend's
multi-select chip filters.

`max_size` (default game_blocks.py's MAX_GAME_BLOCK_SIZE) is Onslaught's
own escape hatch for a bigger overall block -- its own UI requests a
higher cap than the module default so its "team"/"bring back team" size
filters (primary_size up to 5, bringback_size up to 4) have larger blocks
to actually match against.

`games_only=true` skips compute_game_blocks() (and everything downstream
of it) entirely, returning `blocks=[]`/`skipped_games=[]` and just the
`games` list -- Onslaught's own UI calls this once up front to populate
its "Filter by game" chips before the person has picked a game at all,
rather than paying for (and displaying) every game's blocks just to
render a chip row. `games` itself already reflects the full slate
regardless of `team`/`game` (it's built from `eligible_players`, before
either filter is applied -- see below), so this cheap path is always
enough to populate that list.
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
from backend.repositories.salary_multiplier.salary_multiplier_repo import load_multipliers
from backend.schemas.ownership.ownership import GameBlock
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct
from backend.services.ownership.game_blocks import (
    GAME_BLOCK_POSITIONS,
    MIN_GAME_BLOCK_SIZE,
    compute_game_blocks,
    filter_by_bringback_size,
    filter_by_primary_size,
    filter_game_blocks_by_salary_buckets,
)
from backend.services.ownership.game_blocks import MAX_GAME_BLOCK_SIZE as DEFAULT_MAX_GAME_BLOCK_SIZE
from backend.services.ownership.position_blocks import SALARY_CAPS, game_key, game_label
from backend.services.player_selection.engine import filter_selected_players
from backend.services.salary_multiplier.engine import expected_fantasy_points, resolve_multiplier

router = APIRouter()


class GameOption(BaseModel):
    key: str
    label: str


class GameBlocksResult(BaseModel):
    blocks: list[GameBlock]
    games: list[GameOption]
    # Games left out of `blocks` because their own roster was too deep to
    # enumerate under MAX_GAME_BLOCKS_SAFETY_CAP -- see game_blocks.py's
    # compute_game_blocks(). Empty in the common case.
    skipped_games: list[GameOption]


@router.get("/game-blocks", response_model=GameBlocksResult)
def game_blocks_endpoint(
    season: int,
    week: int,
    team: list[str] = Query(default=[]),
    game: list[str] = Query(default=[]),
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    salary_bucket: list[str] = Query(default=[]),
    primary_size: list[int] = Query(default=[]),
    bringback_size: list[int] = Query(default=[]),
    max_size: int = DEFAULT_MAX_GAME_BLOCK_SIZE,
    games_only: bool = False,
) -> GameBlocksResult:
    cap = SALARY_CAPS.get(platform)
    if cap is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown platform '{platform}' -- choose one of {list(SALARY_CAPS)}.",
        )
    if max_size < MIN_GAME_BLOCK_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"max_size must be at least {MIN_GAME_BLOCK_SIZE}.",
        )

    try:
        csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
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

    multiplier = resolve_multiplier(platform, load_multipliers(settings.salary_multiplier_dir).get(platform))
    players = [p.model_copy(update={"expected_fpts": expected_fantasy_points(p.salary, multiplier)}) for p in players]

    overrides = load_overrides(settings.nfl_data_dir, season, week, platform, contest)
    players = filter_selected_players(players, overrides)

    eligible_players = [p for p in players if p.position in GAME_BLOCK_POSITIONS]

    game_options_by_key = {}
    for player in eligible_players:
        key = game_key(player)
        if key not in game_options_by_key:
            game_options_by_key[key] = GameOption(key="-".join(sorted(key)), label=game_label(key))
    games = sorted(game_options_by_key.values(), key=lambda g: g.label)

    if games_only:
        return GameBlocksResult(blocks=[], games=games, skipped_games=[])

    pool = eligible_players
    if team:
        team_set = set(team)
        pool = [p for p in pool if p.team in team_set]
    if game:
        selected_game_keys = {frozenset(g.split("-")) for g in game}
        pool = [p for p in pool if game_key(p) in selected_game_keys]

    blocks, skipped_game_keys = compute_game_blocks(pool, max_size=max_size)
    try:
        blocks = filter_game_blocks_by_salary_buckets(blocks, salary_bucket, cap)
        blocks = filter_by_primary_size(blocks, primary_size)
        blocks = filter_by_bringback_size(blocks, bringback_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    skipped_games = [GameOption(key="-".join(sorted(key)), label=game_label(key)) for key in skipped_game_keys]

    return GameBlocksResult(blocks=blocks, games=games, skipped_games=skipped_games)
