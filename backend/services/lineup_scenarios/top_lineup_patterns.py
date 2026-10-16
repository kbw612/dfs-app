"""
Pattern analysis over the top-N finishing lineups of past Classic contests
-- "what stacks/shapes do winning lineups actually use, and how often?"
Reads the same contest standings + DK salary files the Contest Results tab's
"Contest Top 10 Lineups" panel reads (see contest_results_engine.py's
build_top_lineups), just over many more lineups and several weeks at once,
and counts GENERIC patterns -- position structure only, never team names --
since a specific team stack (e.g. DAL QB/RB/WR) can't repeat across weeks
the way "QB + WR + WR with a WR bring-back" can.

Every lineup is exploded into its 9 players, each resolved by exact name
against that week's DK salary file for true position (so a FLEX slot becomes
RB/WR/TE), team, opponent and salary -- same exact-name join
build_top_lineups itself uses (DK's contest export and salary export use
identical name strings). A lineup with any player that can't be resolved is
skipped entirely (and counted in `lineups_skipped`) rather than analyzed
with a hole in it, since every pattern below depends on all 9 players.

Each lineup contributes at most one occurrence to any given (category,
pattern) pair, so a pattern's count is "lineups containing this pattern" and
its percent is of lineups analyzed. Categories that can legitimately match
several times in one lineup (other game stacks, other team stacks) therefore
don't sum to 100%.

Per pattern we also report trend columns: the average %Drafted of the
pattern's member players (the contest's own actual ownership, summed across
roster slots exactly as the Contest Results table does), the average total
salary of those members (the "salary block"), and the average points of the
lineups that used it. Members are whichever players the pattern is about --
e.g. QB plus his stacked teammates for a QB-stack pattern, the flex player
for a FLEX pattern, the whole lineup for the unused-salary buckets. A
pattern with no members (e.g. "No bring-back") leaves ownership/salary None
rather than inventing a number.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from pydantic import BaseModel

from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.contest_results.contest_results_engine import _total_pct_drafted_by_player
from backend.services.contest_results.contest_standings_parser import ContestStandings, parse_lineup_text

# DK Classic salary cap -- unused salary is measured against it.
SALARY_CAP = 50000
# A "star" is a non-DST player priced at or above this, a "punt" one priced
# at or below the other -- the stars-and-scrubs vs balanced read.
STAR_SALARY = 8000
PUNT_SALARY = 4000

_POSITION_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}


@dataclass(frozen=True)
class WeekInput:
    week: int
    standings: ContestStandings
    salary_players: list[OwnershipPlayer]


@dataclass(frozen=True)
class _Player:
    slot: str
    name: str
    position: str
    team: str
    opponent: str
    salary: int
    own: float | None


class PatternStat(BaseModel):
    pattern: str
    count: int
    pct_of_lineups: float
    by_week: dict[int, int]
    # Mean over this pattern's lineups of the mean %Drafted of its member
    # players. None when the pattern has no members or no ownership data.
    avg_ownership_pct: float | None
    # Mean over this pattern's lineups of its members' summed salaries.
    avg_salary_total: float | None
    avg_points: float


class PatternCategory(BaseModel):
    key: str
    label: str
    description: str
    # Distinct patterns seen in this category, before the per-category cap
    # trimmed `patterns` to the most frequent.
    distinct_patterns: int
    patterns: list[PatternStat]


class TopLineupPatternsResult(BaseModel):
    top_n: int
    weeks_included: list[int]
    weeks_missing: list[int]
    lineups_analyzed: int
    lineups_by_week: dict[int, int]
    lineups_skipped: int
    categories: list[PatternCategory]


# (key, label, description) in display order.
_CATEGORIES: list[tuple[str, str, str]] = [
    ("flex", "FLEX position", "Which position fills the FLEX slot."),
    (
        "stack_size",
        "QB stack size",
        "How many same-team RB/WR/TE teammates are rostered with the QB. Members: QB + those teammates.",
    ),
    (
        "qb_stack",
        "QB stack composition",
        "Which positions are stacked with the QB. Members: QB + those teammates.",
    ),
    (
        "bring_back",
        "Bring-back",
        "Opposing-team RB/WR/TE/QB rostered against the QB's team. Members: the bring-back players.",
    ),
    (
        "game_stack",
        "QB game stack (stack + bring-back)",
        "QB stack composition combined with its bring-back. Members: QB, teammates and bring-back players.",
    ),
    (
        "other_game_stack",
        "Other game stacks (not the QB's game)",
        "Games other than the QB's where the lineup has players from both teams, e.g. a WR against a TE. "
        "A lineup can contain several. Members: those players.",
    ),
    (
        "other_team_stack",
        "Other same-team stacks (not the QB's team)",
        "Two or more same-team RB/WR/TE players on a team other than the QB's. A lineup can contain several.",
    ),
    ("dst_vs", "DST vs lineup players", "Lineup players on the team the DST is facing. Members: DST + those players."),
    ("dst_with", "DST with own offense", "Lineup players on the DST's own team. Members: DST + those players."),
    (
        "salary_shape",
        "Salary shape",
        f"Stars (non-DST priced ${STAR_SALARY:,}+) and punts (non-DST priced ${PUNT_SALARY:,} or less). "
        "Members: those players.",
    ),
    (
        "salary_left",
        "Unused salary",
        f"Salary left under the ${SALARY_CAP:,} cap. Members: the whole lineup.",
    ),
]


def _composition(players: list[_Player]) -> str:
    """"WR + WR + TE" -- positions in QB/RB/WR/TE order, so the same
    structure always yields the same string however the lineup listed it."""
    ordered = sorted(players, key=lambda p: (_POSITION_ORDER.get(p.position, 9), p.position))
    return " + ".join(p.position for p in ordered)


def _lineup_players(
    lineup_text: str, salaries: dict[str, OwnershipPlayer], own_by_player: dict[str, float]
) -> list[_Player] | None:
    players: list[_Player] = []
    for slot, name in parse_lineup_text(lineup_text):
        row = salaries.get(name)
        if row is None:
            return None
        players.append(
            _Player(
                slot=slot,
                name=name,
                position=row.position,
                team=row.team,
                opponent=row.opponent,
                salary=row.salary,
                own=own_by_player.get(name),
            )
        )
    if len(players) != 9:
        return None
    if sum(1 for p in players if p.slot == "QB") != 1 or sum(1 for p in players if p.slot == "DST") != 1:
        return None
    return players


def _lineup_patterns(players: list[_Player]) -> dict[tuple[str, str], list[_Player]]:
    """{(category key, pattern): member players} for one lineup, at most one
    entry per (category, pattern) -- see this module's docstring."""
    out: dict[tuple[str, str], list[_Player]] = {}

    def add(category: str, pattern: str, members: list[_Player]) -> None:
        key = (category, pattern)
        if key in out:
            seen = {id(m) for m in out[key]}
            out[key] = out[key] + [m for m in members if id(m) not in seen]
        else:
            out[key] = list(members)

    qb = next(p for p in players if p.slot == "QB")
    dst = next(p for p in players if p.slot == "DST")
    flex = next((p for p in players if p.slot == "FLEX"), None)
    offense = [p for p in players if p.slot != "DST"]

    if flex is not None:
        add("flex", f"FLEX = {flex.position}", [flex])

    mates = [p for p in offense if p is not qb and p.team == qb.team]
    bring_back = [p for p in offense if p.team == qb.opponent]

    size = len(mates)
    size_label = f"{size} teammate{'' if size == 1 else 's'}" if size < 3 else "3+ teammates"
    add("stack_size", f"QB + {size_label}", [qb, *mates])

    stack_pattern = f"QB + {_composition(mates)}" if mates else "QB alone (no teammate)"
    add("qb_stack", stack_pattern, [qb, *mates])

    bring_pattern = f"Bring-back: {_composition(bring_back)}" if bring_back else "No bring-back"
    add("bring_back", bring_pattern, bring_back)
    add("game_stack", f"{stack_pattern} | {bring_pattern}", [qb, *mates, *bring_back])

    by_team: dict[str, list[_Player]] = defaultdict(list)
    for p in offense:
        by_team[p.team].append(p)

    # Games other than the QB's where both sides have a lineup player.
    seen_games: set[frozenset[str]] = set()
    for team, team_players in by_team.items():
        if team == qb.team or team == qb.opponent:
            continue
        opponent = team_players[0].opponent
        game = frozenset((team, opponent))
        if game in seen_games or opponent not in by_team:
            continue
        seen_games.add(game)
        sides = sorted([_composition(team_players), _composition(by_team[opponent])])
        add("other_game_stack", f"{sides[0]} vs {sides[1]}", [*team_players, *by_team[opponent]])

    for team, team_players in by_team.items():
        if team != qb.team and len(team_players) >= 2:
            add("other_team_stack", _composition(team_players), team_players)

    faced = [p for p in offense if p.team == dst.opponent]
    add("dst_vs", f"DST vs {_composition(faced)}" if faced else "DST vs no lineup players", [dst, *faced])
    own_offense = [p for p in offense if p.team == dst.team]
    add(
        "dst_with",
        f"DST with {_composition(own_offense)}" if own_offense else "DST with no own offense",
        [dst, *own_offense],
    )

    stars = [p for p in offense if p.salary >= STAR_SALARY]
    punts = [p for p in offense if p.salary <= PUNT_SALARY]
    add("salary_shape", f"{len(stars)} stars / {len(punts)} punts", [*stars, *punts])

    left = SALARY_CAP - sum(p.salary for p in players)
    if left < 100:
        bucket = "Under $100 left"
    elif left < 500:
        bucket = "$100-$499 left"
    else:
        bucket = "$500+ left"
    add("salary_left", bucket, players)

    return out


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def analyze_top_lineups(
    week_inputs: list[WeekInput], top_n: int, weeks_missing: list[int] | None = None, max_patterns: int = 25
) -> TopLineupPatternsResult:
    """Counts every pattern across the first `top_n` entries of each week's
    standings (already rank-ascending -- see contest_standings_parser.py).
    `max_patterns` trims each category to its most frequent patterns, ties
    broken alphabetically, so a high-cardinality category (QB game stack)
    doesn't bury the signal."""
    # (category, pattern) -> list of (week, avg own, salary total, points)
    occurrences: dict[tuple[str, str], list[tuple[int, float | None, float | None, float]]] = defaultdict(list)
    lineups_by_week: dict[int, int] = {}
    skipped = 0

    for week_input in week_inputs:
        salaries = {p.player: p for p in week_input.salary_players}
        own_by_player = _total_pct_drafted_by_player(week_input.standings.reference_rows)
        analyzed = 0
        for entry in week_input.standings.entries[:top_n]:
            players = _lineup_players(entry.lineup_text, salaries, own_by_player)
            if players is None:
                skipped += 1
                continue
            analyzed += 1
            for (category, pattern), members in _lineup_patterns(players).items():
                owns = [m.own for m in members if m.own is not None]
                occurrences[(category, pattern)].append(
                    (
                        week_input.week,
                        _mean(owns),
                        float(sum(m.salary for m in members)) if members else None,
                        entry.points,
                    )
                )
        lineups_by_week[week_input.week] = analyzed

    total = sum(lineups_by_week.values())
    weeks = sorted(lineups_by_week)
    categories: list[PatternCategory] = []
    for key, label, description in _CATEGORIES:
        stats: list[PatternStat] = []
        for (category, pattern), rows in occurrences.items():
            if category != key:
                continue
            owns = [r[1] for r in rows if r[1] is not None]
            salaries_total = [r[2] for r in rows if r[2] is not None]
            by_week = {w: sum(1 for r in rows if r[0] == w) for w in weeks}
            stats.append(
                PatternStat(
                    pattern=pattern,
                    count=len(rows),
                    pct_of_lineups=100.0 * len(rows) / total if total else 0.0,
                    by_week=by_week,
                    avg_ownership_pct=_mean(owns),
                    avg_salary_total=_mean(salaries_total),
                    avg_points=sum(r[3] for r in rows) / len(rows),
                )
            )
        stats.sort(key=lambda s: (-s.count, s.pattern))
        categories.append(
            PatternCategory(
                key=key,
                label=label,
                description=description,
                distinct_patterns=len(stats),
                patterns=stats[:max_patterns],
            )
        )

    return TopLineupPatternsResult(
        top_n=top_n,
        weeks_included=weeks,
        weeks_missing=weeks_missing or [],
        lineups_analyzed=total,
        lineups_by_week=lineups_by_week,
        lineups_skipped=skipped,
        categories=categories,
    )
