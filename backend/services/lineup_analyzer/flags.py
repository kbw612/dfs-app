"""
Lineup flags for the Lineup Analyzer. Each lineup (9 cells in slot order QB,
RB, RB, WR, WR, WR, TE, FLEX, DST) gets zero or more flags. Flags only mark;
they never remove or block a lineup.

Errors:   over_cap, not_on_slate, duplicate_player, invalid_slot
Warnings: dst_conflict, injury, duplicate_lineup
Notes:    no_qb_stack, low_total_weather, big_underdog, too_many_punts,
          ownership_extreme, near_duplicate, same_team_rbs, starter_risk

Lineups that can't be fully matched to the slate (not on the slate, repeated
player) only get their errors -- the rest need every player known.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from backend.schemas.lineup_analyzer.flags import FlagSettings, FlagSummary, LineupFlag
from backend.services.lineup_analyzer.history_loader import HistoricalPlayer
from backend.services.shared.name_match import normalize_player_name

SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
SALARY_CAP = 50000
_SLOT_POSITIONS = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "DST": {"DST"}, "FLEX": {"RB", "WR", "TE"}}
INJURY_CODES = {"O", "D", "IR", "IR-R"}
BAD_WEATHER_COLORS = {"orange", "red"}
# Depth-chart rank at or past which a starter is a risk, per position.
_STARTER_RISK_RANK = {"QB": 2, "RB": 3, "WR": 4, "TE": 2}

# code -> (severity, label), in display order.
FLAG_DEFS: dict[str, tuple[str, str]] = {
    "over_cap": ("error", "Over the salary cap"),
    "not_on_slate": ("error", "Player not on this slate"),
    "duplicate_player": ("error", "Duplicate player"),
    "invalid_slot": ("error", "Position doesn't fit slot"),
    "dst_conflict": ("warning", "Offense vs own DST"),
    "injury": ("warning", "Injury status"),
    "duplicate_lineup": ("warning", "Duplicate lineup"),
    "no_qb_stack": ("note", "No QB stack"),
    "low_total_weather": ("note", "Low-total or bad-weather game"),
    "big_underdog": ("note", "Big underdog DST or RB"),
    "too_many_punts": ("note", "Too many punts"),
    "ownership_extreme": ("note", "Ownership extreme"),
    "near_duplicate": ("note", "Near-duplicate lineup"),
    "same_team_rbs": ("note", "Same-team RBs"),
    "starter_risk": ("note", "Starter risk"),
}

Cell = tuple[str, str]  # (name, dk id)


@dataclass
class FlagContext:
    pool: dict[str, HistoricalPlayer]
    id_to_name: dict[str, str]
    injury: dict[str, str] = field(default_factory=dict)  # normalized name -> status code
    depth: dict[str, int] = field(default_factory=dict)  # normalized name -> depth rank
    lines: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # team -> (own, opp implied, total)
    bad_weather_teams: set[str] = field(default_factory=set)
    settings: FlagSettings = field(default_factory=FlagSettings)
    own_low: float | None = None  # lineups below / above these total ownerships are extremes
    own_high: float | None = None
    near_dup_counts: dict[tuple[str, ...], int] = field(default_factory=dict)


@dataclass
class FlaggedLineup:
    index: int  # position in the raw pool
    key: tuple[str, ...] | None  # sorted canonical names when fully resolved, else None
    names: list[str | None]  # canonical name per slot (None = not on slate)
    raw: list[Cell]
    flags: list[LineupFlag]


def canonical_name(name: str, pid: str, ctx: FlagContext) -> str | None:
    """The slate player a cell refers to, the way the scorer resolves it."""
    first = ctx.id_to_name.get(pid) or name.strip()
    if first in ctx.pool:
        return first
    text = name.strip()  # DST fallback: the text may say "Las Vegas Raiders"
    return next((n for n, p in ctx.pool.items() if p.position == "DST" and (text.endswith(n) or n.endswith(text))), None)


def _flag(code: str, text: str) -> LineupFlag:
    severity, label = FLAG_DEFS[code]
    return LineupFlag(code=code, severity=severity, label=label, text=text)


def _money(n: int) -> str:
    return f"${n:,}"


def _own_sum(players: list[HistoricalPlayer]) -> float:
    return sum(p.actual_pct for p in players)


def injury_lookup(depth_snapshot) -> dict[str, str]:
    """Normalized name -> status code for players whose depth-chart status
    means Out, Doubtful or IR."""
    out: dict[str, str] = {}
    for team in (depth_snapshot.teams if depth_snapshot else []):
        for players in team.positions.values():
            for p in players:
                if p.status in INJURY_CODES:
                    out[normalize_player_name(p.player)] = p.status
    return out


def bad_weather_teams(weather_snapshot) -> set[str]:
    """Teams in a game the weather scrape colors orange or red."""
    out: set[str] = set()
    for g in (weather_snapshot.games if weather_snapshot else []):
        if g.color.lower() in BAD_WEATHER_COLORS:
            out.update(t for t in (g.away_team, g.home_team) if t)
    return out


def own_bounds(own_sums: list[float], slice_pct: float) -> tuple[float | None, float | None]:
    if not own_sums or slice_pct <= 0:
        return None, None
    arr = np.array(own_sums)
    return float(np.percentile(arr, slice_pct)), float(np.percentile(arr, 100 - slice_pct))


def near_duplicate_counts(keys: list[tuple[str, ...]]) -> dict[tuple[str, ...], int]:
    """Lineups that share 8 of 9 players with another, by key."""
    buckets: dict[tuple[str, ...], list[int]] = {}
    for i, key in enumerate(keys):
        for drop in range(len(key)):
            buckets.setdefault(key[:drop] + key[drop + 1 :], []).append(i)
    others: dict[int, set[int]] = {}
    for members in buckets.values():
        if len(members) > 1:
            for a in members:
                others.setdefault(a, set()).update(m for m in members if m != a)
    return {keys[a]: len(b) for a, b in others.items()}


def flag_lineup(raw: list[Cell], copies: int, ctx: FlagContext) -> FlaggedLineup:
    names = [canonical_name(n, pid, ctx) for n, pid in raw]
    flags: list[LineupFlag] = []

    missing = [raw[i][0] for i, n in enumerate(names) if n is None]
    if missing:
        flags.append(_flag("not_on_slate", "Not on this slate: " + ", ".join(missing)))
    present = [n for n in names if n is not None]
    repeats = [n for n, c in Counter(present).items() if c > 1]
    if repeats:
        flags.append(_flag("duplicate_player", "Listed more than once: " + ", ".join(repeats)))
    if missing or repeats:
        return FlaggedLineup(0, None, names, raw, flags)

    players = [ctx.pool[n] for n in names]  # type: ignore[index]
    s = ctx.settings

    salary = sum(p.salary for p in players)
    if salary > SALARY_CAP:
        flags.append(_flag("over_cap", f"Salary {_money(salary)} is {_money(salary - SALARY_CAP)} over the cap"))
    for slot, p in zip(SLOTS, players):
        if p.position not in _SLOT_POSITIONS[slot]:
            flags.append(_flag("invalid_slot", f"{p.name} ({p.position}) can't play {slot}"))

    offense = players[:8]
    dst = players[8]

    faced = [p.name for p in offense if dst.opponent and p.team == dst.opponent]
    if faced:
        flags.append(_flag("dst_conflict", f"{', '.join(faced)} face your DST ({dst.name})"))

    hurt = [f"{p.name} ({ctx.injury[normalize_player_name(p.name)]})" for p in players if normalize_player_name(p.name) in ctx.injury]
    if hurt:
        flags.append(_flag("injury", ", ".join(hurt)))

    if copies > 1:
        flags.append(_flag("duplicate_lineup", f"Uploaded {copies} times; the extra copies were dropped"))

    qb = players[0]
    if not any(p.team == qb.team for p in offense[1:]):
        flags.append(_flag("no_qb_stack", f"{qb.name} has no teammate RB, WR or TE"))

    games: list[str] = []
    for p in offense:
        total = ctx.lines.get(p.team, (0.0, 0.0, 0.0))[2]
        reasons = []
        if total and total < s.low_total:
            reasons.append(f"total {total:g}")
        if p.team in ctx.bad_weather_teams:
            reasons.append("bad weather")
        if reasons:
            label = f"{p.team} vs {p.opponent} ({', '.join(reasons)})"
            if label not in games:
                games.append(label)
    if games:
        flags.append(_flag("low_total_weather", "; ".join(games)))

    dogs = []
    for p in [*(q for q in offense if q.position == "RB"), dst]:
        own, opp, _ = ctx.lines.get(p.team, (0.0, 0.0, 0.0))
        if opp and own and opp - own >= s.underdog_spread:
            dogs.append(f"{p.name} ({p.team}, {opp - own:.1f}-point underdog)")
    if dogs:
        flags.append(_flag("big_underdog", ", ".join(dogs)))

    punts = [p.name for p in offense if p.salary <= s.punt_salary]
    if len(punts) >= s.punt_count:
        flags.append(_flag("too_many_punts", f"{len(punts)} players at {_money(s.punt_salary)} or less: {', '.join(punts)}"))

    total_own = _own_sum(players)
    if ctx.own_high is not None and total_own > ctx.own_high:
        flags.append(_flag("ownership_extreme", f"Total ownership {total_own:.0f}% is in the top {s.own_slice_pct:g}% of this pool"))
    elif ctx.own_low is not None and total_own < ctx.own_low:
        flags.append(_flag("ownership_extreme", f"Total ownership {total_own:.0f}% is in the bottom {s.own_slice_pct:g}% of this pool"))

    key = tuple(sorted(n for n in names if n))  # type: ignore[misc]
    near = ctx.near_dup_counts.get(key, 0)
    if near:
        flags.append(_flag("near_duplicate", f"Differs from {near} other lineup{'s' if near != 1 else ''} by one player"))

    by_team = Counter(p.team for p in offense if p.position == "RB")
    twins = [t for t, c in by_team.items() if c >= 2]
    if twins:
        flags.append(_flag("same_team_rbs", "Two RBs from " + ", ".join(twins)))

    risky = []
    for p in offense:
        rank = ctx.depth.get(normalize_player_name(p.name))
        limit = _STARTER_RISK_RANK.get(p.position)
        if rank and limit and rank >= limit:
            risky.append(f"{p.name} ({p.position}{rank})")
    if risky:
        flags.append(_flag("starter_risk", ", ".join(risky) + " on the depth chart"))

    return FlaggedLineup(0, key, names, raw, flags)


def flag_pool(raw_lineups: list[list[Cell]], copies: list[int], ctx: FlagContext) -> list[FlaggedLineup]:
    """Flags every lineup. Two passes: pool-wide figures (ownership slice, near
    duplicates) need every lineup resolved first."""
    first = [flag_lineup(raw, 1, ctx) for raw in raw_lineups]
    keys = [f.key for f in first if f.key is not None]
    ctx.near_dup_counts = near_duplicate_counts(keys)
    own_sums = [_own_sum([ctx.pool[n] for n in f.names if n]) for f in first if f.key is not None]
    ctx.own_low, ctx.own_high = own_bounds(own_sums, ctx.settings.own_slice_pct)
    out = []
    for i, raw in enumerate(raw_lineups):
        flagged = flag_lineup(raw, copies[i] if i < len(copies) else 1, ctx)
        flagged.index = i
        out.append(flagged)
    return out


def summarize(flagged: list[FlaggedLineup]) -> list[FlagSummary]:
    counts = Counter(code for f in flagged for code in {fl.code for fl in f.flags})
    return [FlagSummary(code=c, severity=sev, label=label, count=counts[c]) for c, (sev, label) in FLAG_DEFS.items()]
