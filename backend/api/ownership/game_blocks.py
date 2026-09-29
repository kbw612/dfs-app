"""
GET /game-blocks?season=&week=&team=&game=&platform=&salary_bucket=&bringback_size=&include_qb=
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

Filtering order matches /position-blocks: Settings' Player Selection
(`apply_selection_filter`, default true) -> My Player Pool's own saved
shortlist (`apply_my_player_pool_filter`, default false) -> team (optional)
-> game (optional) -> compute_game_blocks() decides the combinations ->
salary_bucket (post-filter on generated blocks) -> primary_size/
bringback_size (also post-filters). `team`/`game`/`salary_bucket`/
`primary_size`/`bringback_size` are all repeatable query params, matching
the frontend's multi-select chip filters. The two pool filters are
independent and both optional, same as /position-blocks -- see that
endpoint's docstring for why that's a deliberate difference from Boom/
Bust's mutually-exclusive all-vs-selected toggle.

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

`include_qb` (default True -- Onslaught's own UI offers this as a toggle,
defaulted on) adds one QB from either team in the game as an extra slot on
top of each RB/WR/TE combination (see game_blocks.py's compute_game_blocks
docstring for the exact rule). QB rows are gathered separately from
`eligible_players` (which stays RB/WR/TE-only, same as before, since it
also drives the "Filter by game" chip list) and merged into the pool
passed to compute_game_blocks only when this is on.

Every returned block's own total_salary is also always capped at
`cap - cheapest_dst_salary_this_contest` (see game_blocks.py's
filter_game_blocks_by_max_salary) -- a block that spends more than that
could never actually be finished into a real DK lineup, since every
lineup still needs a DST on top, and the contest's own cheapest DST sets
the floor for how much that has to cost. `cheapest_dst_salary` comes from
this contest's own DK salary file (`salary_snapshot`, loaded further down)
-- the raw, unfiltered slate, not narrowed by Player Selection/My Player
Pool, since "the cheapest DST on the contest" means literally that. Not a
toggle -- always applied. A contest with no DST rows at all in its salary
file (shouldn't happen in practice) skips this cap entirely rather than
filtering out every block.
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
from backend.repositories.my_player_pool.my_player_pool_repo import load_membership
from backend.repositories.player_selection.player_selection_repo import load_overrides
from backend.repositories.salary_multiplier.salary_multiplier_repo import load_multipliers
from backend.schemas.ownership.ownership import GameBlock, OwnershipPlayer
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.dk_salary.ownership_enrich import enrich_with_ownership_pct
from backend.services.my_player_pool.engine import in_my_player_pool
from backend.services.ownership.game_blocks import (
    GAME_BLOCK_POSITIONS,
    GAME_BLOCK_QB_POSITION,
    MIN_GAME_BLOCK_SIZE,
    compute_game_blocks,
    filter_by_bringback_size,
    filter_by_primary_size,
    filter_game_blocks_by_max_salary,
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
    # cap - cheapest_dst_salary_this_contest -- every block in `blocks`
    # already has total_salary <= this (see this module's own docstring
    # and filter_game_blocks_by_max_salary), surfaced here purely so the
    # frontend can explain the cap in its own hint text rather than
    # silently returning fewer blocks. None only when this contest's own
    # salary file has no DST rows at all (the cap isn't applied then).
    max_onslaught_salary: int | None = None


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
    apply_selection_filter: bool = True,
    apply_my_player_pool_filter: bool = False,
    include_qb: bool = True,
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

    # The contest's own cheapest DST, straight off the raw salary file --
    # not narrowed by Player Selection/My Player Pool (see this module's
    # own docstring: "the cheapest DST on the contest" means literally
    # every DST in the slate, regardless of either pool filter below).
    # None only when this contest's salary file somehow has no DST rows at
    # all, in which case the cap is skipped entirely rather than zeroing
    # out every block.
    dst_salaries = [p.salary for p in salary_snapshot.players if p.position == "DST"]
    max_onslaught_salary = cap - min(dst_salaries) if dst_salaries else None

    ownership_snapshot_path = find_latest_ownership_snapshot(settings.ownership_snapshots_dir, season=season, week=week)
    ownership_players = load_ownership_snapshot(ownership_snapshot_path).players if ownership_snapshot_path else None
    players = enrich_with_ownership_pct(salary_snapshot.players, ownership_players)

    multiplier = resolve_multiplier(platform, load_multipliers(settings.salary_multiplier_dir).get(platform))
    players = [p.model_copy(update={"expected_fpts": expected_fantasy_points(p.salary, multiplier)}) for p in players]

    if apply_selection_filter:
        overrides = load_overrides(settings.nfl_data_dir, season, week, platform, contest)
        players = filter_selected_players(players, overrides)

    if apply_my_player_pool_filter:
        membership = load_membership(settings.nfl_data_dir, season, week, platform, contest)
        players = [p for p in players if in_my_player_pool(p.player, membership)]

    eligible_players = [p for p in players if p.position in GAME_BLOCK_POSITIONS]

    game_options_by_key = {}
    # A representative player per matchup -- game_label() needs one to know
    # which side is home (see position_blocks.py's game_label docstring).
    # Built from `eligible_players` (the full, unfiltered slate) rather
    # than `pool` below, so it still covers every key skipped_game_keys
    # could ever contain even after team/game filtering narrows `pool`.
    representative_player_by_key: dict[frozenset[str], OwnershipPlayer] = {}
    for player in eligible_players:
        key = game_key(player)
        representative_player_by_key.setdefault(key, player)
        if key not in game_options_by_key:
            game_options_by_key[key] = GameOption(key="-".join(sorted(key)), label=game_label(player))
    games = sorted(game_options_by_key.values(), key=lambda g: g.label)

    if games_only:
        return GameBlocksResult(blocks=[], games=games, skipped_games=[], max_onslaught_salary=max_onslaught_salary)

    pool = eligible_players
    qb_pool = [p for p in players if p.position == GAME_BLOCK_QB_POSITION]
    if team:
        team_set = set(team)
        pool = [p for p in pool if p.team in team_set]
        qb_pool = [p for p in qb_pool if p.team in team_set]
    if game:
        selected_game_keys = {frozenset(g.split("-")) for g in game}
        pool = [p for p in pool if game_key(p) in selected_game_keys]
        qb_pool = [p for p in qb_pool if game_key(p) in selected_game_keys]

    blocks, skipped_game_keys = compute_game_blocks(pool + qb_pool, max_size=max_size, include_qb=include_qb)
    if max_onslaught_salary is not None:
        blocks = filter_game_blocks_by_max_salary(blocks, max_onslaught_salary)
    try:
        blocks = filter_game_blocks_by_salary_buckets(blocks, salary_bucket, cap)
        blocks = filter_by_primary_size(blocks, primary_size)
        blocks = filter_by_bringback_size(blocks, bringback_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    skipped_games = [
        GameOption(key="-".join(sorted(key)), label=game_label(representative_player_by_key[key]))
        for key in skipped_game_keys
    ]

    return GameBlocksResult(
        blocks=blocks, games=games, skipped_games=skipped_games, max_onslaught_salary=max_onslaught_salary
    )
