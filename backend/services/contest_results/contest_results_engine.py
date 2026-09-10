"""
Joins parsed ContestStandings (contest_standings_parser.py) against the
week's DK salary file to build this feature's two outputs -- see
backend/schemas/contest_results/contest_results.py's own docstring for
what each one is. Both need a per-player Salary/true-Position lookup from
the salary file (a list[OwnershipPlayer], same shape Salary Blocks/Player
Pool already read -- see backend/services/dk_salary/dk_salary_loader.py);
build_top_lineups additionally needs Exp Pts and the export's own Act
Pts/%Drafted lookup.

Exp Pts is a fixed salary * 4 / 1000 -- deliberately its OWN constant
(EXP_PTS_MULTIPLIER below), not backend/services/salary_multiplier/
engine.py's shared, Settings-overridable multiplier that Player Rankings/
Salary Blocks read. This is a look-back analysis of a specific past
contest; it should keep reading the same fixed "4x" every time, not
silently shift if someone later tunes Settings' Salary Multiplier field
for unrelated, forward-looking reasons.
"""

from __future__ import annotations

from backend.schemas.contest_results.contest_results import (
    ContestResultRow,
    LineupGameStack,
    LineupPlayer,
    LineupSummary,
    TopLineup,
)
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.contest_results.contest_standings_parser import (
    ContestReferenceRow,
    ContestStandings,
    parse_lineup_text,
)
from backend.services.ownership.position_blocks import game_key

# See this module's own docstring for why this is its own fixed constant
# rather than reading Settings' Salary Multiplier field.
EXP_PTS_MULTIPLIER = 4.0

# DraftKings Classic's own salary cap -- used for LineupSummary.salary_leftover.
SALARY_CAP = 50000

# How far Diff (Act Pts - Exp Pts) has to swing before a player counts as
# a "boom" or "bust" for LineupPlayer.boom_bust -- a fixed absolute-points
# threshold rather than a percentage of Exp Pts, so it means the same
# thing regardless of the player's salary. Deliberately not user-tunable,
# same reasoning as EXP_PTS_MULTIPLIER above.
BOOM_BUST_THRESHOLD = 5.0

# Positions considered for LineupGameStack -- DST is deliberately excluded
# (its own team's correlation is LineupSummary.dst_team/dst_teammates
# instead, a different question than "which game did this player's stats
# come from").
GAME_STACK_POSITIONS = {"QB", "RB", "WR", "TE"}


def _salary_lookup(players: list[OwnershipPlayer]) -> dict[str, OwnershipPlayer]:
    """DK's own contest export and its own salary export use the exact
    same player-name strings -- including DST's team-nickname-only naming
    (e.g. "Packers", not "Green Bay Packers") -- since both come straight
    from DraftKings itself. A plain exact-name match is enough; no fuzzy
    matching attempted."""
    return {p.player: p for p in players}


def _reference_lookups(
    reference_rows: list[ContestReferenceRow],
) -> tuple[dict[tuple[str, str], ContestReferenceRow], dict[str, ContestReferenceRow]]:
    """Two lookups off the same rows: by (player, roster_position) exact
    slot match first -- the %Drafted for THIS specific slot usage --
    falling back to by-player-only (first row found) for a lineup that
    used a player in a slot the reference table itself never broke out
    separately. Act Pts is the same real number either way (a player's
    own actual score doesn't depend on which slot they were drafted at)
    -- only %Drafted actually differs by slot."""
    by_slot: dict[tuple[str, str], ContestReferenceRow] = {}
    by_player: dict[str, ContestReferenceRow] = {}
    for row in reference_rows:
        by_slot.setdefault((row.player, row.roster_position), row)
        by_player.setdefault(row.player, row)
    return by_slot, by_player


class _RankInfo:
    """Internal only -- (position, ownership_rank, points_rank) for one
    player, not a Pydantic model since this never leaves the engine."""

    __slots__ = ("position", "ownership_rank", "points_rank")

    def __init__(self, position: str | None, ownership_rank: int | None, points_rank: int | None) -> None:
        self.position = position
        self.ownership_rank = ownership_rank
        self.points_rank = points_rank


def _build_player_rank_lookup(
    reference_rows: list[ContestReferenceRow],
    salary_lookup: dict[str, OwnershipPlayer],
) -> dict[str, _RankInfo]:
    """Ranks every rostered player against others at their own true
    `position` (from the salary file, NOT roster_position -- a player used
    at both RB and FLEX across different entries should only count once,
    under RB) -- both by total %Drafted (ownership_rank, 1 = most-owned)
    and by actual FPTS (points_rank, 1 = highest-scoring). A player with
    no salary-file match has no known position and is left out of both
    rankings entirely (there's no group to rank them within).

    %Drafted is SUMMED across every roster slot a player was used in --
    the real-world quirk that motivated this (see
    contest_standings_parser.py) is a player like a flex-eligible RB
    showing up as two separate reference rows, one for RB and one for
    FLEX, each with their own partial %Drafted -- their *total* usage
    rate is what "the Nth-most-owned RB" should mean, not either slot's
    own smaller number. FPTS is a real player's one actual score for the
    week -- every slot's row already carries the same value, so the last
    one seen wins (they should never disagrees)."""
    positions: dict[str, str] = {}
    total_pct: dict[str, float] = {}
    fpts_by_player: dict[str, float] = {}

    for row in reference_rows:
        salary_row = salary_lookup.get(row.player)
        if salary_row is None:
            continue
        positions[row.player] = salary_row.position
        total_pct[row.player] = total_pct.get(row.player, 0.0) + row.pct_drafted
        fpts_by_player[row.player] = row.fpts

    by_position: dict[str, list[str]] = {}
    for player, position in positions.items():
        by_position.setdefault(position, []).append(player)

    ownership_rank: dict[str, int] = {}
    points_rank: dict[str, int] = {}
    for players in by_position.values():
        for rank, player in enumerate(sorted(players, key=lambda p: total_pct[p], reverse=True), start=1):
            ownership_rank[player] = rank
        for rank, player in enumerate(sorted(players, key=lambda p: fpts_by_player[p], reverse=True), start=1):
            points_rank[player] = rank

    return {
        player: _RankInfo(
            position=positions[player],
            ownership_rank=ownership_rank.get(player),
            points_rank=points_rank.get(player),
        )
        for player in positions
    }


def _build_game_stacks(
    lineup_players: list[LineupPlayer],
    salary_lookup: dict[str, OwnershipPlayer],
) -> list[LineupGameStack]:
    """Groups this lineup's QB/RB/WR/TE players (see GAME_STACK_POSITIONS)
    by which NFL game they played in, using game_key() -- the same
    per-game identifier Salary Blocks' Onslaught feature uses (see
    backend/services/ownership/game_blocks.py) -- then labels each game
    with 2+ lineup players as either "onslaught" (both teams represented,
    same primary/bring-back split Onslaught itself uses) or this
    feature's own "overstack" (only one team represented). A game with
    just 1 lineup player isn't a stack of any kind and is left out
    entirely."""
    groups: dict[frozenset[str], dict[str, list[str]]] = {}
    for p in lineup_players:
        if p.position not in GAME_STACK_POSITIONS:
            continue
        salary_row = salary_lookup.get(p.player)
        if salary_row is None:
            continue
        key = game_key(salary_row)
        groups.setdefault(key, {}).setdefault(salary_row.team, []).append(p.position)

    stacks: list[LineupGameStack] = []
    for by_team in groups.values():
        total = sum(len(positions) for positions in by_team.values())
        if total < 2:
            continue
        if len(by_team) == 1:
            team = next(iter(by_team))
            stacks.append(
                LineupGameStack(
                    kind="overstack",
                    primary_team=team,
                    primary_positions=by_team[team],
                    bringback_team=None,
                    bringback_positions=[],
                )
            )
        else:
            # Larger side is primary; an even split breaks alphabetically
            # by team, same convention as game_blocks.py's _to_game_block.
            (team_a, positions_a), (team_b, positions_b) = sorted(by_team.items())
            if len(positions_a) >= len(positions_b):
                primary_team, primary_positions = team_a, positions_a
                bringback_team, bringback_positions = team_b, positions_b
            else:
                primary_team, primary_positions = team_b, positions_b
                bringback_team, bringback_positions = team_a, positions_a
            stacks.append(
                LineupGameStack(
                    kind="onslaught",
                    primary_team=primary_team,
                    primary_positions=primary_positions,
                    bringback_team=bringback_team,
                    bringback_positions=bringback_positions,
                )
            )

    stacks.sort(key=lambda s: len(s.primary_positions) + len(s.bringback_positions), reverse=True)
    return stacks


def _build_lineup_summary(
    lineup_players: list[LineupPlayer],
    salary_lookup: dict[str, OwnershipPlayer],
    total_salary: int,
) -> LineupSummary:
    flex_row = next((p for p in lineup_players if p.roster_position == "FLEX"), None)
    flex_position = flex_row.position if flex_row else None

    dst_row = next((p for p in lineup_players if p.roster_position == "DST"), None)
    dst_salary_row = salary_lookup.get(dst_row.player) if dst_row else None
    dst_team = dst_salary_row.team if dst_salary_row else None
    dst_opponent_team = dst_salary_row.opponent if dst_salary_row else None
    dst_teammates = (
        [
            p.player
            for p in lineup_players
            if p is not dst_row and p.player in salary_lookup and salary_lookup[p.player].team == dst_team
        ]
        if dst_team is not None
        else []
    )
    dst_opponent_positions = (
        [
            salary_lookup[p.player].position
            for p in lineup_players
            if p is not dst_row and p.player in salary_lookup and salary_lookup[p.player].team == dst_opponent_team
        ]
        if dst_opponent_team is not None
        else []
    )

    qb_row = next((p for p in lineup_players if p.roster_position == "QB"), None)
    qb_salary_row = salary_lookup.get(qb_row.player) if qb_row else None
    qb_player = qb_row.player if qb_row else None
    qb_team = qb_salary_row.team if qb_salary_row else None
    qb_stacked = (
        any(
            p is not qb_row and p.player in salary_lookup and salary_lookup[p.player].team == qb_team
            for p in lineup_players
        )
        if qb_team is not None
        else None
    )

    matched_salary_rows = [salary_lookup[p.player] for p in lineup_players if p.player in salary_lookup]
    distinct_teams = len({row.team for row in matched_salary_rows})
    distinct_games = len({game_key(row) for row in matched_salary_rows})

    salary_leftover = (
        SALARY_CAP - total_salary if all(p.salary is not None for p in lineup_players) else None
    )

    return LineupSummary(
        flex_position=flex_position,
        game_stacks=_build_game_stacks(lineup_players, salary_lookup),
        dst_team=dst_team,
        dst_teammates=dst_teammates,
        dst_opponent_team=dst_opponent_team,
        dst_opponent_positions=dst_opponent_positions,
        qb_player=qb_player,
        qb_stacked=qb_stacked,
        distinct_games=distinct_games,
        distinct_teams=distinct_teams,
        salary_leftover=salary_leftover,
    )


def build_top_lineups(
    standings: ContestStandings,
    salary_players: list[OwnershipPlayer],
    top_n: int,
) -> list[TopLineup]:
    """The first `top_n` entries, in the export's own row order (already
    rank-ascending -- see contest_standings_parser.py's docstring), each
    exploded into its 9 (roster_position, player) pairs and joined
    against the salary file and the export's own reference table. A
    player who doesn't match either lookup gets None fields rather than
    dropping the row entirely -- a lineup should always show all 9 slots,
    even if one player's own numbers are unavailable."""
    salaries = _salary_lookup(salary_players)
    by_slot, by_player = _reference_lookups(standings.reference_rows)
    # Computed once for the whole contest (not per lineup) -- every
    # lineup's players are ranked against the same contest-wide pool.
    rank_lookup = _build_player_rank_lookup(standings.reference_rows, salaries)

    lineups: list[TopLineup] = []
    for entry in standings.entries[:top_n]:
        total_salary = 0
        total_pct = 0.0
        total_exp = 0.0
        total_act = 0.0
        lineup_players: list[LineupPlayer] = []

        for roster_position, name in parse_lineup_text(entry.lineup_text):
            salary_row = salaries.get(name)
            ref_row = by_slot.get((name, roster_position)) or by_player.get(name)

            salary = salary_row.salary if salary_row else None
            position = salary_row.position if salary_row else None
            pct_drafted = ref_row.pct_drafted if ref_row else None
            act_pts = ref_row.fpts if ref_row else None
            exp_pts = salary * EXP_PTS_MULTIPLIER / 1000 if salary is not None else None
            diff = (act_pts - exp_pts) if (act_pts is not None and exp_pts is not None) else None

            boom_bust = None
            if diff is not None:
                if diff >= BOOM_BUST_THRESHOLD:
                    boom_bust = "boom"
                elif diff <= -BOOM_BUST_THRESHOLD:
                    boom_bust = "bust"

            rank_info = rank_lookup.get(name)

            lineup_players.append(
                LineupPlayer(
                    roster_position=roster_position,
                    player=name,
                    salary=salary,
                    position=position,
                    pct_drafted=pct_drafted,
                    exp_pts=exp_pts,
                    act_pts=act_pts,
                    diff=diff,
                    ownership_rank=rank_info.ownership_rank if rank_info else None,
                    points_rank=rank_info.points_rank if rank_info else None,
                    boom_bust=boom_bust,
                )
            )
            if salary is not None:
                total_salary += salary
            if pct_drafted is not None:
                total_pct += pct_drafted
            if exp_pts is not None:
                total_exp += exp_pts
            if act_pts is not None:
                total_act += act_pts

        lineups.append(
            TopLineup(
                rank=entry.rank,
                entry_name=entry.entry_name,
                points=entry.points,
                players=lineup_players,
                total_salary=total_salary,
                total_pct_drafted=total_pct,
                total_exp_pts=total_exp,
                total_act_pts=total_act,
                total_diff=total_act - total_exp,
                summary=_build_lineup_summary(lineup_players, salaries, total_salary),
            )
        )
    return lineups


def build_contest_result_rows(
    standings: ContestStandings,
    salary_players: list[OwnershipPlayer],
    week: int,
) -> list[ContestResultRow]:
    """Every reference row (see contest_standings_parser.py), reformatted
    with Salary joined in and `week` attached -- one row per distinct
    player+roster-slot combination the contest actually saw, same order
    the export itself already sorted them in (%Drafted descending)."""
    salaries = _salary_lookup(salary_players)
    rows: list[ContestResultRow] = []
    for ref in standings.reference_rows:
        salary_row = salaries.get(ref.player)
        rows.append(
            ContestResultRow(
                week=week,
                player=ref.player,
                salary=salary_row.salary if salary_row else None,
                roster_position=ref.roster_position,
                pct_drafted=ref.pct_drafted,
                fpts=ref.fpts,
            )
        )
    return rows
