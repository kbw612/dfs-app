"""
Four derived views computed over a single OwnershipSnapshot (DK
salary/ownership projections for one season+week -- see
backend/schemas/ownership/ownership.py), plus a diff between two
snapshots of that *same* week. Ported from the uploaded
high_owned_players.py notebook's pandas logic into the same pure-Python,
config-driven style as usage_bump/engine.py -- no pandas, no CSV
round-tripping.

1. compute_high_owned() -- "chalk": every player owned above a threshold
   that scales down as the slate gets bigger (config/
   ownership-leverage-tiers.json, loaded via leverage_tiers_repo.py). A
   1-game slate needs 50%+ ownership to count as chalk; an 8+-game Sunday
   only needs 20%+, since ownership naturally spreads thinner across more
   players.

2. compute_game_leverage() -- one group per NFL game that has at least
   one chalk player on either side, containing every chalk player from
   both teams (`chalk_players`) and every player from both teams whose
   ownership is currently *below* the leverage point (`pivot_candidates`)
   -- the contrarian plays worth pairing against that game's chalk. This
   collapses the original notebook's per-team-with-chalk loop (which
   could produce two overlapping groups for a single game if both teams
   had chalk) into one group per unique game. QBs/DSTs are excluded
   entirely (see GAME_LEVERAGE_EXCLUDED_POSITIONS).

3. compute_pivots() -- for every player (not just chalk ones -- matches
   the notebook's final, most-filtered version rather than the looser one
   embedded partway through), every same-position player within
   `salary_tolerance` and owned at least `ownership_gap` points less. A
   same-position, similar-price, much-less-owned fade.

4. compute_multi_leverage() -- reads the output of #2 and #3 (not the raw
   player list) to find players who are worth fading/pivoting off of 2+
   other players at once, combining both mechanisms into one count. The
   frontend used to derive this client-side; moved here so the API is the
   single source of truth for it, matching #1-#3.

Every function takes plain data in and returns plain data out -- no I/O,
no config loading -- so they're trivially testable and the API layer
decides where the snapshot/config actually come from.
"""

from __future__ import annotations

from backend.repositories.ownership.leverage_tiers_repo import LeverageTier
from backend.schemas.ownership.ownership import (
    GameLeverageGroup,
    LeverageReason,
    MultiLeveragePlayer,
    OwnershipChange,
    OwnershipPlayer,
    OwnershipSnapshot,
    PivotGroup,
)

DEFAULT_SALARY_TOLERANCE = 500
DEFAULT_OWNERSHIP_GAP = 10.0

# Game Leverage is about stacking/fading skill-position exposure within a
# game -- QBs and DSTs are excluded entirely (never chalk, never a pivot
# candidate) since they're single-per-team roster slots with very
# different ownership dynamics than the FLEX-eligible pool this section is
# meant for. Chalk (compute_high_owned) and Pivots (compute_pivots) are
# unaffected -- this exclusion is scoped to compute_game_leverage only.
GAME_LEVERAGE_EXCLUDED_POSITIONS = {"QB", "DST"}


def _resolve_leverage_point(num_games: float, tiers: list[LeverageTier]) -> float:
    for tier in tiers:
        if num_games >= tier.min_games and (tier.max_games is None or num_games <= tier.max_games):
            return tier.leverage_point
    raise ValueError(
        f"No leverage tier configured for a {num_games}-game slate -- see "
        "config/ownership-leverage-tiers.json"
    )


def compute_high_owned(
    players: list[OwnershipPlayer], tiers: list[LeverageTier]
) -> tuple[list[OwnershipPlayer], float]:
    """(chalk players, the leverage point used to decide "chalk" for this
    slate). Slate size is inferred from how many distinct teams appear in
    `players` -- a team on bye simply won't show up, so it naturally drops
    out of the game count."""
    num_teams = len({p.team for p in players})
    num_games = num_teams / 2
    leverage_point = _resolve_leverage_point(num_games, tiers)

    high_owned = [p for p in players if p.ownership_pct > leverage_point]
    return high_owned, leverage_point


def compute_game_leverage(players: list[OwnershipPlayer], leverage_point: float) -> list[GameLeverageGroup]:
    """One GameLeverageGroup per unique game (team + opponent, unordered)
    that has at least one chalk player on either side. `team`/`opponent`
    on the group are just the pair sorted alphabetically for a stable,
    arbitrary label -- each player's own `is_home` still says who's
    actually hosting. QBs and DSTs are excluded entirely (see
    GAME_LEVERAGE_EXCLUDED_POSITIONS) -- a game with chalk only at those
    positions produces no group at all."""
    eligible = [p for p in players if p.position not in GAME_LEVERAGE_EXCLUDED_POSITIONS]

    games: dict[frozenset[str], list[OwnershipPlayer]] = {}
    for player in eligible:
        game_key = frozenset({player.team, player.opponent})
        games.setdefault(game_key, []).append(player)

    groups: list[GameLeverageGroup] = []
    for game_key, game_players in games.items():
        chalk_players = [p for p in game_players if p.ownership_pct > leverage_point]
        if not chalk_players:
            continue

        pivot_candidates = [p for p in game_players if p.ownership_pct < leverage_point]
        team, opponent = sorted(game_key) if len(game_key) == 2 else (next(iter(game_key)), "")
        groups.append(
            GameLeverageGroup(
                team=team,
                opponent=opponent,
                chalk_players=chalk_players,
                pivot_candidates=pivot_candidates,
            )
        )

    return groups


def compute_pivots(
    players: list[OwnershipPlayer],
    salary_tolerance: int = DEFAULT_SALARY_TOLERANCE,
    ownership_gap: float = DEFAULT_OWNERSHIP_GAP,
) -> list[PivotGroup]:
    """One PivotGroup per player who has at least one same-position,
    similar-salary, meaningfully-less-owned alternative -- players with no
    qualifying pivot are omitted entirely rather than appearing with an
    empty list."""
    groups: list[PivotGroup] = []
    for trigger in players:
        pivots = [
            candidate
            for candidate in players
            if candidate.player != trigger.player
            and candidate.position == trigger.position
            and abs(candidate.salary - trigger.salary) <= salary_tolerance
            and candidate.ownership_pct <= trigger.ownership_pct - ownership_gap
        ]
        if not pivots:
            continue

        pivots.sort(key=lambda p: p.salary, reverse=True)
        groups.append(PivotGroup(trigger=trigger, pivots=pivots))

    return groups


def compute_multi_leverage(
    pivots: list[PivotGroup], game_leverage: list[GameLeverageGroup]
) -> list[MultiLeveragePlayer]:
    """Every player who's worth fading/pivoting off of 2+ other players at
    once, combining both mechanisms into one count -- a player who's the
    pivot for one trigger AND a game-leverage pick against one chalk
    player already qualifies, even though those are two different
    mechanisms; what matters is the total. One LeverageReason per
    relationship: each PivotGroup a player appears in as a pivot
    contributes one ("kind"="pivot"), and each *chalk player* in a
    GameLeverageGroup a player appears in as a pivot_candidate contributes
    one ("kind"="game") -- so fading a game with 2 chalk players is worth
    2 reasons, not 1. Sorted by reason count descending, then salary
    descending within a tie (the frontend also buckets by reason count for
    display -- see OwnershipView.tsx's groupMultiLeveragePlayers -- but the
    counting/qualifying logic itself lives here, not there)."""
    by_name: dict[str, MultiLeveragePlayer] = {}

    def add_reason(player: OwnershipPlayer, reason: LeverageReason) -> None:
        existing = by_name.get(player.player)
        if existing:
            existing.reasons.append(reason)
        else:
            by_name[player.player] = MultiLeveragePlayer(player=player, reasons=[reason])

    for group in pivots:
        for pivot in group.pivots:
            add_reason(pivot, LeverageReason(kind="pivot", against=group.trigger))

    for group in game_leverage:
        for candidate in group.pivot_candidates:
            for chalk in group.chalk_players:
                add_reason(
                    candidate,
                    LeverageReason(kind="game", against=chalk, team=group.team, opponent=group.opponent),
                )

    qualifying = [entry for entry in by_name.values() if len(entry.reasons) >= 2]
    qualifying.sort(key=lambda e: (-len(e.reasons), -e.player.salary))
    return qualifying


def compute_ownership_diff(old_snapshot: OwnershipSnapshot, new_snapshot: OwnershipSnapshot) -> list[OwnershipChange]:
    """Compares two snapshots of the *same* (season, week) -- e.g. two
    scrapes taken hours apart -- and returns every player whose ownership
    and/or salary changed, plus anyone added to or dropped from the page
    entirely (change_types=["other"], matching depth_charts.Change's
    convention for additions/removals). Matched by player name alone,
    since team/position/opponent don't change within a single week."""
    old_index = {p.player: p for p in old_snapshot.players}
    new_index = {p.player: p for p in new_snapshot.players}

    changes: list[OwnershipChange] = []
    for name in sorted(set(old_index) | set(new_index)):
        old_player = old_index.get(name)
        new_player = new_index.get(name)

        if old_player and new_player:
            change_types: list[str] = []
            if old_player.ownership_pct != new_player.ownership_pct:
                change_types.append("ownership")
            if old_player.salary != new_player.salary:
                change_types.append("salary")
            if not change_types:
                continue

            changes.append(
                OwnershipChange(
                    player=name,
                    position=new_player.position,
                    team=new_player.team,
                    opponent=new_player.opponent,
                    change_types=change_types,
                    previous_ownership_pct=old_player.ownership_pct,
                    current_ownership_pct=new_player.ownership_pct,
                    previous_salary=old_player.salary,
                    current_salary=new_player.salary,
                )
            )
        elif new_player and not old_player:
            changes.append(
                OwnershipChange(
                    player=name,
                    position=new_player.position,
                    team=new_player.team,
                    opponent=new_player.opponent,
                    change_types=["other"],
                    current_ownership_pct=new_player.ownership_pct,
                    current_salary=new_player.salary,
                )
            )
        elif old_player and not new_player:
            changes.append(
                OwnershipChange(
                    player=name,
                    position=old_player.position,
                    team=old_player.team,
                    opponent=old_player.opponent,
                    change_types=["other"],
                    previous_ownership_pct=old_player.ownership_pct,
                    previous_salary=old_player.salary,
                )
            )

    return changes
