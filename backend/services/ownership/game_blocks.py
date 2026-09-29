"""
Onslaught blocks -- unlike position_blocks.py's single-position
combinations (e.g. "every pair of RBs on the slate"), these are *game*
blocks: any mix of RB/WR/TE players from a single NFL game, drawn from
BOTH teams (never all one side) -- a "game stack." QB/DST are excluded,
same reasoning as position_blocks.py's own ALLOWED_BLOCK_SIZES
(single-per-team roster slots, different ownership/salary dynamics than
the FLEX-eligible pool this is about).

Onslaught is the raw pool of these combinations -- any split between the
two teams, as long as both appear at least once -- filterable by either
side's own player count via filter_by_primary_size()/
filter_by_bringback_size() (Onslaught's own UI offers 1-5 for the larger
"team" side and 1-4 for the smaller "bring back team" side).
`primary_team`/`primary_count`/`bringback_team`/`bringback_count` are
computed the same way regardless of which filter is in use: whichever
team has more players in a given block is "primary," the other is "bring
back." max_size (default MAX_GAME_BLOCK_SIZE, but Onslaught's own UI
requests a higher one -- see backend/api/ownership/game_blocks.py)
controls how large a block's total size can get; there's no assumption
baked in here about what range that leaves either side's own count in,
since callers can and do ask for different caps.

Same combinatorial-blowup concern as position_blocks.py (a game's full
RB/WR/TE pool across both teams is larger than any single position's own
pool, so this has its own, higher MAX_GAME_BLOCKS_SAFETY_CAP rather than
reusing position_blocks.py's -- a realistic post-Player-Selection game
roster (10-20ish RB/WR/TE across both teams) already produces several
thousand both-teams combinations across sizes 2-5, well past that
module's single-position-tuned cap).

Unlike position_blocks.py, an over-cap game here doesn't fail the whole
request -- compute_game_blocks() skips just that one game (returned
separately as `skipped_games`) and still returns every other game's
blocks. Onslaught is meant to be browsed "across the whole slate" by
default (see backend/api/ownership/game_blocks.py), so one unusually deep
game's roster shouldn't block seeing every other game's blocks or even
populate the game-filter chips at all -- narrowing by team or game is how
you'd bring that one game back under the cap, not a prerequisite for
using this endpoint at all.

`include_qb` (default False here; the API layer's own default is True --
see backend/api/ownership/game_blocks.py) adds exactly one QB from either
team in the game on top of each RB/WR/TE combination -- an extra slot, not
counted against `min_size`/`max_size`. When more than one QB is eligible
for a game (one per team), a separate block is generated per QB candidate,
same "every combination, not just one pick" philosophy as the RB/WR/TE
side. A game with zero eligible QBs simply produces no blocks at all while
`include_qb` is on (not a `skipped_games` case -- same class as a game
whose eligible pool never resolved to both teams, see the <2-teams check
below).
"""

from __future__ import annotations

from itertools import combinations
from math import comb

from backend.schemas.ownership.ownership import GameBlock, OwnershipPlayer
from backend.services.ownership.position_blocks import game_key, salary_bucket_range

MIN_GAME_BLOCK_SIZE = 2
MAX_GAME_BLOCK_SIZE = 5

GAME_BLOCK_POSITIONS = {"RB", "WR", "TE"}

# The one position `include_qb` adds on top of GAME_BLOCK_POSITIONS -- kept
# as its own constant (not folded into GAME_BLOCK_POSITIONS) since a QB is
# always exactly one extra slot per block, never part of the RB/WR/TE
# combination sizing (see this module's docstring).
GAME_BLOCK_QB_POSITION = "QB"

# Deliberately much higher than position_blocks.py's MAX_BLOCKS_SAFETY_CAP
# (2,000) -- that cap was tuned for a single position's players at one
# game (typically single digits to low teens), where a few thousand
# combinations already signals a filtering mistake. This module's pool is
# 2-3 positions combined across both teams, so a legitimate, well-filtered
# request routinely produces tens of thousands of combinations -- this cap
# is only meant to catch a genuinely unfiltered, whole-roster request (50+
# players in one game), not normal use.
MAX_GAME_BLOCKS_SAFETY_CAP = 25000


def _both_teams_combo_count(team_counts: dict[str, int], size: int) -> int:
    """How many `size`-combinations of this game's pool include at least
    one player from each team -- every combination minus the ones drawn
    entirely from one team or the other, computed directly via comb()
    rather than generating and filtering, so the safety-cap check below
    never has to materialize anything first."""
    total = len(team_counts) and sum(team_counts.values())
    if total < size:
        return 0
    all_combos = comb(total, size)
    same_team_combos = sum(comb(count, size) for count in team_counts.values() if count >= size)
    return all_combos - same_team_combos


def _to_game_block(combo: tuple[OwnershipPlayer, ...]) -> GameBlock:
    team_counts: dict[str, int] = {}
    for p in combo:
        team_counts[p.team] = team_counts.get(p.team, 0) + 1

    # Larger count is "primary"; smaller is "bring-back". An even split
    # (e.g. 2-2) breaks alphabetically by team so the same split always
    # labels the same way instead of flip-flopping combo to combo.
    (team_a, count_a), (team_b, count_b) = sorted(team_counts.items())
    if count_a >= count_b:
        primary_team, primary_count, bringback_team, bringback_count = team_a, count_a, team_b, count_b
    else:
        primary_team, primary_count, bringback_team, bringback_count = team_b, count_b, team_a, count_a

    # QB (when include_qb added one) always shown first, regardless of
    # salary -- it's a distinct "extra slot" on top of the RB/WR/TE combo
    # (see this module's docstring), so it reads better pinned to the top
    # rather than sorted in wherever its salary happens to land. Everyone
    # else keeps the existing highest-salary-first order.
    players = sorted(combo, key=lambda p: (p.position != GAME_BLOCK_QB_POSITION, -p.salary))
    return GameBlock(
        players=players,
        total_salary=sum(p.salary for p in players),
        total_expected_fpts=sum(p.expected_fpts or 0.0 for p in players),
        primary_team=primary_team,
        primary_count=primary_count,
        bringback_team=bringback_team,
        bringback_count=bringback_count,
    )


def compute_game_blocks(
    players: list[OwnershipPlayer],
    min_size: int = MIN_GAME_BLOCK_SIZE,
    max_size: int = MAX_GAME_BLOCK_SIZE,
    include_qb: bool = False,
) -> tuple[list[GameBlock], list[frozenset[str]]]:
    """(blocks, skipped_games). `players` should already be filtered to
    whatever team/game the caller wants (this module doesn't apply any of
    its own team/game filtering beyond bucketing by game) -- this only
    decides how to group the RB/WR/TE pool into both-teams-represented
    combinations.

    `include_qb` (see this module's docstring) adds one QB from either
    team in the game as an extra slot on top of each RB/WR/TE combination
    -- `players` should include QB rows too when this is True (they're
    otherwise ignored, same as DST already is).

    skipped_games is every game whose own combination count exceeded
    MAX_GAME_BLOCKS_SAFETY_CAP -- that one game is left out of `blocks`
    entirely (not truncated to a partial/misleading subset), while every
    other game's blocks still come back normally. See this module's
    docstring for why this skips rather than raising."""
    eligible = [p for p in players if p.position in GAME_BLOCK_POSITIONS]

    games: dict[frozenset[str], list[OwnershipPlayer]] = {}
    for p in eligible:
        games.setdefault(game_key(p), []).append(p)

    qbs_by_game: dict[frozenset[str], list[OwnershipPlayer]] = {}
    if include_qb:
        for p in players:
            if p.position == GAME_BLOCK_QB_POSITION:
                qbs_by_game.setdefault(game_key(p), []).append(p)

    blocks: list[GameBlock] = []
    skipped_games: list[frozenset[str]] = []
    for key, game_players in games.items():
        team_counts: dict[str, int] = {}
        for p in game_players:
            team_counts[p.team] = team_counts.get(p.team, 0) + 1
        # A game whose eligible pool only ever resolved to one team (a bye,
        # or incomplete opponent data) can never produce a both-teams
        # block at any size -- skip it rather than feeding size checks
        # numbers that can only ever come out to 0 anyway. Not counted as
        # a "skipped" game -- that label is reserved for the safety-cap
        # case below, a completely different reason for having no blocks.
        if len(team_counts) < 2:
            continue

        # With include_qb on, a game with no eligible QB at all can't
        # produce a single block (every block now requires one) -- same
        # "no blocks, not a safety-cap skip" treatment as the <2-teams
        # case just above, not `skipped_games`.
        game_qbs = qbs_by_game.get(key, [])
        if include_qb and not game_qbs:
            continue

        sizes = [k for k in range(min_size, max_size + 1) if k <= len(game_players)]
        qb_multiplier = len(game_qbs) if include_qb else 1
        total_combos = sum(_both_teams_combo_count(team_counts, k) for k in sizes) * qb_multiplier
        if total_combos > MAX_GAME_BLOCKS_SAFETY_CAP:
            skipped_games.append(key)
            continue

        for k in sizes:
            for combo in combinations(game_players, k):
                if len({p.team for p in combo}) < 2:
                    continue
                if include_qb:
                    for qb in game_qbs:
                        blocks.append(_to_game_block(combo + (qb,)))
                else:
                    blocks.append(_to_game_block(combo))

    blocks.sort(key=lambda b: b.total_salary, reverse=True)
    return blocks, skipped_games


def filter_by_bringback_size(blocks: list[GameBlock], sizes: list[int]) -> list[GameBlock]:
    """Keep only blocks whose bring-back (minority) side is exactly one of
    the requested sizes -- Onslaught's own "bring back team" filter (see
    this module's docstring). An empty `sizes` means "no filter" --
    returns `blocks` unchanged."""
    if not sizes:
        return blocks
    size_set = set(sizes)
    return [b for b in blocks if b.bringback_count in size_set]


def filter_by_primary_size(blocks: list[GameBlock], sizes: list[int]) -> list[GameBlock]:
    """Same idea as filter_by_bringback_size, but for the majority
    ("primary"/"team") side -- Onslaught's own "team" filter. An empty
    `sizes` means "no filter" -- returns `blocks` unchanged."""
    if not sizes:
        return blocks
    size_set = set(sizes)
    return [b for b in blocks if b.primary_count in size_set]


def filter_game_blocks_by_max_salary(blocks: list[GameBlock], max_salary: int) -> list[GameBlock]:
    """Keeps only blocks whose own combined salary leaves at least enough
    room under the cap for the rest of a real lineup -- specifically, the
    caller passes `max_salary = cap - cheapest_dst_salary_on_the_slate`
    (see backend/api/ownership/game_blocks.py), since every Onslaught
    block still needs a DST added on top of it to become a real lineup, and
    there's no point surfacing a block that can never actually fit one.
    Inclusive (<=) -- a block landing exactly on that boundary still leaves
    exactly enough room."""
    return [b for b in blocks if b.total_salary <= max_salary]


def filter_game_blocks_by_salary_buckets(blocks: list[GameBlock], bucket_ids: list[str], cap: int) -> list[GameBlock]:
    """Same percent-of-cap bucket filter as position_blocks.py's
    filter_blocks_by_salary_buckets, duplicated here (rather than shared)
    since it's a two-line body and the two functions filter different
    block types -- not worth a generic/Protocol type just to share it."""
    if not bucket_ids:
        return blocks

    ranges = [salary_bucket_range(bucket_id, cap) for bucket_id in bucket_ids]

    def matches(block: GameBlock) -> bool:
        return any(
            block.total_salary >= min_dollar and (max_dollar is None or block.total_salary < max_dollar)
            for min_dollar, max_dollar in ranges
        )

    return [block for block in blocks if matches(block)]
