"""
Leverage & Pivots rules, shared by the selected-player columns and the panel
so they cannot drift apart. Pure functions: players in, finished rows out.

For a trigger player T (any owned player):

- Leverage: T's own offense plus the defense T faces (for a DST trigger, the
  offense it faces), excluding QBs, owned below the chalk line and 10+ points less than T.
- Correlated: the opposing team's RBs, WRs and TEs (any ownership). Explorer
  only -- never a panel reason. Empty for a DST trigger.
- Position pivot: same position, within $500, owned 10+ points less than T,
  in a different game.
- Pricing pivot: a different position (no QBs), same price and ownership
  rules, different game.
"""

from __future__ import annotations

from backend.schemas.leverage_pivots.leverage_pivots import (
    LpChalkGroup,
    LpColumn,
    LpPanelGroup,
    LpPanelPlayer,
    LpPlayer,
    LpReason,
    LpRow,
    LpSelected,
)
from backend.schemas.ownership.ownership import OwnershipPlayer

SALARY_TOLERANCE = 500
OWNERSHIP_GAP = 10.0
POSITION_ORDER = ["QB", "RB", "WR", "TE", "DST"]
_REASON_LABELS = {"leverage": "Leverage", "position_pivot": "Position pivot", "pricing_pivot": "Pricing pivot"}


def _game(p: OwnershipPlayer) -> frozenset[str]:
    return frozenset({p.team, p.opponent})


def _card(p: OwnershipPlayer) -> LpPlayer:
    return LpPlayer(
        player=p.player, position=p.position, team=p.team, opponent=p.opponent,
        salary=p.salary, ownership_pct=p.ownership_pct if p.ownership_pct is not None else 0.0,
    )


def _money(value: int) -> str:
    return f"${abs(value):,}"


def _diff_label(candidate: int, trigger: int) -> str:
    diff = candidate - trigger
    if diff == 0:
        return "($0)"
    return f"(+{_money(diff)})" if diff > 0 else f"(−{_money(diff)})"


def _less_label(candidate: OwnershipPlayer, trigger: OwnershipPlayer) -> str | None:
    own, base = candidate.ownership_pct or 0.0, trigger.ownership_pct or 0.0
    if base <= 0:
        return None
    pct = round((base - own) / base * 100)
    n = round(base / own) if own > 0 else 0
    return f"1/{n} · {pct}% less" if n >= 2 else f"{pct}% less"


def _owned(players: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
    return [p for p in players if p.ownership_pct is not None]


def leverage_for(t: OwnershipPlayer, players: list[OwnershipPlayer], leverage_point: float) -> list[OwnershipPlayer]:
    out = []
    for c in players:
        if c.player == t.player or c.position == "QB" or c.ownership_pct >= leverage_point or c.ownership_pct > t.ownership_pct - OWNERSHIP_GAP:
            continue
        if t.position == "DST":
            if c.team == t.opponent and c.position != "DST":
                out.append(c)
        elif c.team == t.team and c.position != "DST":
            out.append(c)
        elif c.team == t.opponent and c.position == "DST":
            out.append(c)
    return sorted(out, key=lambda c: c.salary, reverse=True)


def correlated_for(t: OwnershipPlayer, players: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
    if t.position == "DST":
        return []
    out = [c for c in players if c.team == t.opponent and c.position in ("RB", "WR", "TE")]
    return sorted(out, key=lambda c: c.ownership_pct, reverse=True)


def _pivot_candidates(t: OwnershipPlayer, players: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
    return [
        c for c in players
        if c.player != t.player
        and _game(c) != _game(t)
        and abs(c.salary - t.salary) <= SALARY_TOLERANCE
        and c.ownership_pct <= t.ownership_pct - OWNERSHIP_GAP
    ]


def position_pivots_for(t: OwnershipPlayer, players: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
    return sorted((c for c in _pivot_candidates(t, players) if c.position == t.position), key=lambda c: c.salary, reverse=True)


def pricing_pivots_for(t: OwnershipPlayer, players: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
    return sorted(
        (c for c in _pivot_candidates(t, players) if c.position != t.position and c.position != "QB"),
        key=lambda c: c.salary, reverse=True,
    )


def _row(c: OwnershipPlayer, t: OwnershipPlayer, with_less: bool) -> LpRow:
    return LpRow(**_card(c).model_dump(), salary_diff_label=_diff_label(c.salary, t.salary),
                 less_label=_less_label(c, t) if with_less else None)


def build_selected(
    t: OwnershipPlayer, players: list[OwnershipPlayer], leverage_point: float, position: str | None = None
) -> LpSelected:
    lev = leverage_for(t, players, leverage_point)
    cor = correlated_for(t, players)
    pos = position_pivots_for(t, players)
    pri = pricing_pivots_for(t, players)

    counts: dict[str, int] = {}
    for c in (*lev, *cor, *pos, *pri):
        counts[c.position] = counts.get(c.position, 0) + 1

    def keep(rows: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
        return [c for c in rows if position in (None, "", "All") or c.position == position]

    is_dst = t.position == "DST"
    return LpSelected(
        trigger=_card(t),
        game_label=f"{t.team} vs {t.opponent}",
        leverage=LpColumn(
            title="Leverage",
            subtitle="The defense it's facing, and its own offense." if is_dst else "Same offense, or the defense it's facing.",
            header=f"{t.opponent} offense" if is_dst else f"{t.team} + {t.opponent} DST",
            rows=[_row(c, t, True) for c in keep(lev)],
        ),
        correlated=LpColumn(
            title="Correlated", subtitle="Opposing RBs, WRs and TEs in the same game.",
            header=f"{t.opponent} offense", rows=[_row(c, t, False) for c in keep(cor)],
        ),
        position_pivot=LpColumn(
            title="Position pivot", subtitle="Same position, within $500, 10% less owned, different game.",
            header=f"{t.position} within $500", rows=[_row(c, t, True) for c in keep(pos)],
        ),
        pricing_pivot=LpColumn(
            title="Pricing pivot", subtitle="Any other position, within $500, 10% less owned, different game.",
            header="Other positions", rows=[_row(c, t, True) for c in keep(pri)],
        ),
        position_counts=[(p, counts[p]) for p in POSITION_ORDER if p in counts],
    )


def build_chalk_groups(chalk: list[OwnershipPlayer]) -> list[LpChalkGroup]:
    groups = []
    for pos in POSITION_ORDER:
        members = sorted((p for p in chalk if p.position == pos), key=lambda p: p.ownership_pct, reverse=True)
        if members:
            groups.append(LpChalkGroup(position=pos, players=[_card(p) for p in members]))
    return groups


def build_panel(players: list[OwnershipPlayer], leverage_point: float, min_reasons: int = 2) -> list[LpPanelGroup]:
    """Players with `min_reasons`+ reasons, each reason one trigger (every owned RB, WR
    and TE -- QBs and DSTs are left out of the panel, as both triggers and
    listed players) they are leverage or a position/pricing pivot against.
    No cap on reasons."""
    players = [p for p in players if p.position not in ("QB", "DST")]
    by_name: dict[str, tuple[OwnershipPlayer, list[LpReason]]] = {}

    def add(c: OwnershipPlayer, kind: str, text: str) -> None:
        by_name.setdefault(c.player, (c, []))[1].append(LpReason(kind=kind, label=_REASON_LABELS[kind], text=text))

    for t in sorted(players, key=lambda p: p.ownership_pct, reverse=True):
        who = f"{t.player} {t.position} · {t.ownership_pct:.1f}% owned"
        for c in leverage_for(t, players, leverage_point):
            add(c, "leverage", f"{who} · " + ("defense it faces" if t.position == "DST" else "same offense" if c.team == t.team else "defense he faces"))
        for c in position_pivots_for(t, players):
            add(c, "position_pivot", f"{who} · {_money(t.salary)}")
        for c in pricing_pivots_for(t, players):
            add(c, "pricing_pivot", f"{who} · {_money(t.salary)}")

    qualifying = [(c, r) for c, r in by_name.values() if len(r) >= max(1, min_reasons)]
    qualifying.sort(key=lambda e: (-len(e[1]), -e[0].salary))
    groups: dict[int, list[LpPanelPlayer]] = {}
    for c, reasons in qualifying:
        groups.setdefault(len(reasons), []).append(LpPanelPlayer(**_card(c).model_dump(), reasons=reasons))
    return [LpPanelGroup(reason_count=n, players=groups[n]) for n in sorted(groups, reverse=True)]


def owned_players(players: list[OwnershipPlayer]) -> list[OwnershipPlayer]:
    return _owned(players)
