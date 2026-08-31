"""
Position Blocks: every fixed-size, same-position combination of players
(e.g. all 3-RB groups) with each group's combined salary -- lets you scan
"blocks" of same-position plays by total cost rather than one player at a
time.

Ported from the uploaded contest_player_stacks_v2.py script's
build_player_combinations_df()/build_player_combo_stacks(), which is
really just "itertools.combinations + sum salary + sort" underneath a lot
of scaffolding specific to that script's old Colab workflow: separate
GitHub CSV fetchers for player pool/receivers/RBs, a hand-curated "upside
players" shortlist merged in to keep the combination count small, and
O(n^2) nested-loop pair-finding (get_player_stacks/
get_same_team_player_stacks) for a *different*, unused feature in that
script. None of that carries over -- this app already has
salary/position/team/opponent for every player via the already-loaded
OwnershipSnapshot (see backend/api/ownership/position_blocks.py), and a
single itertools.combinations pass replaces the nested loops. The
script's own combinations call was dead code (computed, never used); this
is the corrected version of what it was trying to do.

compute_position_blocks() takes an already-filtered candidate pool (the
API layer applies position/team/game filters before calling this) and
either:
  - same_game_only=False: every block_size-combination across the whole
    pool, regardless of matchup, or
  - same_game_only=True: players are first bucketed by game (a canonical
    key from team+opponent, same convention as
    ownership/engine.py's compute_game_leverage), and combinations are
    generated within each bucket separately -- never mixing players from
    different games into the same block.

Every block's players are sorted by salary descending, and the returned
list is sorted by total_salary descending, matching the script's own
sort order.

Combinations grow combinatorially (20 players choose 3 = 1,140; choose 4
= 4,845), so this raises ValueError rather than silently computing a
huge list if a candidate pool would produce more than
MAX_BLOCKS_SAFETY_CAP combinations -- the fix is narrower team/position/
game filters, not a truncated result silently missing data. This is a
backstop against pathological inputs, not a normal-use UX limiter.
"""

from __future__ import annotations

from itertools import combinations
from math import comb

from backend.schemas.ownership.ownership import OwnershipPlayer, PositionBlock

MAX_BLOCKS_SAFETY_CAP = 2000

# Which block sizes make sense per position -- QB/DST aren't here at all
# (single-per-team roster slots, same reasoning as
# ownership/engine.py's GAME_LEVERAGE_EXCLUDED_POSITIONS), and the sizes
# themselves reflect how many of each position a DK roster actually
# starts: 1 mandatory TE (blocks of 2 = "TE vs the field"), 2 mandatory
# RBs (blocks of 2 or 3, the 3rd covering FLEX), 3 mandatory WRs (blocks
# of 2, 3, or 4, the 4th covering FLEX).
ALLOWED_BLOCK_SIZES: dict[str, list[int]] = {
    "RB": [2, 3],
    "WR": [2, 3, 4],
    "TE": [2],
}


def validate_block_size(position: str, block_size: int) -> None:
    allowed = ALLOWED_BLOCK_SIZES.get(position)
    if allowed is None:
        raise ValueError(f"Position blocks aren't supported for position '{position}' -- choose RB, WR, or TE.")
    if block_size not in allowed:
        raise ValueError(f"Block size {block_size} isn't valid for {position} -- choose one of {allowed}.")


# DFS platforms' full-roster salary cap -- only DraftKings has real data
# behind it today, but keeping this as a name -> cap lookup (rather than
# hardcoding 50000 inline) means adding FanDuel later is a one-line
# addition here, not a schema change. Deliberately *only* affects the
# salary-bucket filter below -- ALLOWED_BLOCK_SIZES and everything else in
# this module still assumes DK's roster construction regardless of which
# platform is selected; that's a real gap, not an oversight, and gets
# fixed when FanDuel data actually shows up rather than guessed at now.
SALARY_CAPS: dict[str, int] = {
    "DraftKings": 50000,
    "FanDuel": 60000,
}

# Percent-of-cap buckets for filtering blocks by how much of the full
# lineup budget they'd use, expressed as [min_pct, max_pct) -- None for
# max_pct means "and up". Percent, not a flat dollar range, is the
# portable unit across platforms with different caps (see SALARY_CAPS);
# the dollar bounds for a given platform are derived from these at request
# time via salary_bucket_range(), never stored directly.
SALARY_BUCKETS: list[tuple[str, float, float | None]] = [
    ("under_20", 0.0, 20.0),
    ("20_30", 20.0, 30.0),
    ("30_40", 30.0, 40.0),
    ("40_50", 40.0, 50.0),
    ("50_60", 50.0, 60.0),
    ("60_plus", 60.0, None),
]

_SALARY_BUCKETS_BY_ID = {bucket_id: (min_pct, max_pct) for bucket_id, min_pct, max_pct in SALARY_BUCKETS}


def salary_bucket_range(bucket_id: str, cap: int) -> tuple[float, float | None]:
    """(min_dollar, max_dollar) for one bucket under a specific platform's
    cap -- max_dollar is None for the open-ended top bucket."""
    if bucket_id not in _SALARY_BUCKETS_BY_ID:
        raise ValueError(f"Unknown salary bucket '{bucket_id}' -- choose one of {list(_SALARY_BUCKETS_BY_ID)}.")
    min_pct, max_pct = _SALARY_BUCKETS_BY_ID[bucket_id]
    min_dollar = cap * min_pct / 100
    max_dollar = cap * max_pct / 100 if max_pct is not None else None
    return min_dollar, max_dollar


def filter_blocks_by_salary_buckets(
    blocks: list[PositionBlock], bucket_ids: list[str], cap: int
) -> list[PositionBlock]:
    """Keeps blocks whose total_salary falls in *any* of the selected
    buckets (a block matching one of several picked ranges still counts).
    An empty bucket_ids list means "no filter" -- returns `blocks`
    unchanged, not an empty list."""
    if not bucket_ids:
        return blocks

    ranges = [salary_bucket_range(bucket_id, cap) for bucket_id in bucket_ids]

    def matches(block: PositionBlock) -> bool:
        return any(
            block.total_salary >= min_dollar and (max_dollar is None or block.total_salary < max_dollar)
            for min_dollar, max_dollar in ranges
        )

    return [block for block in blocks if matches(block)]


def game_key(player: OwnershipPlayer) -> frozenset[str]:
    """Canonical per-game identifier -- both teams in a matchup map to the
    same key, same convention as compute_game_leverage()'s game_key."""
    return frozenset({player.team, player.opponent})


def game_label(key: frozenset[str]) -> str:
    """'ARI vs LAR' -- alphabetically sorted so it's stable regardless of
    which side of the matchup you start from."""
    teams = sorted(key)
    return " vs ".join(teams) if len(teams) == 2 else next(iter(teams), "")


def _blocks_from_pool(pool: list[OwnershipPlayer], block_size: int) -> list[PositionBlock]:
    num_combinations = comb(len(pool), block_size) if len(pool) >= block_size else 0
    if num_combinations > MAX_BLOCKS_SAFETY_CAP:
        raise ValueError(
            f"{len(pool)} players choose {block_size} is {num_combinations:,} blocks -- "
            "narrow the team/position/game filters before generating blocks."
        )

    blocks: list[PositionBlock] = []
    for combo in combinations(pool, block_size):
        players = sorted(combo, key=lambda p: p.salary, reverse=True)
        blocks.append(PositionBlock(players=players, total_salary=sum(p.salary for p in players)))
    return blocks


def compute_position_blocks(
    players: list[OwnershipPlayer],
    block_size: int,
    same_game_only: bool,
) -> list[PositionBlock]:
    """`players` should already be filtered to one position (and any
    team/game filters) by the caller -- this only decides how to bucket
    and combine them."""
    if same_game_only:
        buckets: dict[frozenset[str], list[OwnershipPlayer]] = {}
        for player in players:
            buckets.setdefault(game_key(player), []).append(player)

        blocks: list[PositionBlock] = []
        for bucket_players in buckets.values():
            blocks.extend(_blocks_from_pool(bucket_players, block_size))
    else:
        blocks = _blocks_from_pool(players, block_size)

    blocks.sort(key=lambda b: b.total_salary, reverse=True)
    return blocks
