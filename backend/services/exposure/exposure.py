"""
Exposure calculation: given a set of lineups, how often each player appears,
how the FLEX slot splits across RB/WR/TE, and how that compares with field
ownership. Pure functions -- callers supply lineups and lookups.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.schemas.exposure.exposure import (
    ExposurePlayer,
    ExposureResult,
    ExposureScope,
    ExposureView,
    FlexCount,
)

SORTS = ("exposure", "diff", "pts", "salary")


@dataclass(frozen=True)
class LineupPlayer:
    slot: str  # QB, RB, WR, TE, FLEX or DST
    name: str
    position: str  # the player's true position (what a FLEX player really is)
    team: str
    salary: int


def build_exposure(
    key: str,
    label: str,
    lineups: list[list[LineupPlayer]],
    field_pct: dict[str, float] | None = None,
    pts: dict[str, float] | None = None,
    compare_pct: dict[str, float] | None = None,
) -> ExposureResult:
    n = len(lineups)
    counts: dict[str, int] = {}
    meta: dict[str, LineupPlayer] = {}
    flex = {"RB": 0, "WR": 0, "TE": 0}
    for lineup in lineups:
        for p in lineup:
            counts[p.name] = counts.get(p.name, 0) + 1
            meta.setdefault(p.name, p)
            if p.slot == "FLEX" and p.position in flex:
                flex[p.position] += 1
    flex_total = sum(flex.values())
    players = []
    for name, count in counts.items():
        p = meta[name]
        exposure = count / n * 100.0
        field = field_pct.get(name) if field_pct else None
        players.append(
            ExposurePlayer(
                name=name,
                team=p.team,
                position=p.position,
                salary=p.salary,
                count=count,
                exposure_pct=round(exposure, 1),
                field_pct=None if field is None else round(field, 1),
                diff=None if field is None else round(exposure - field, 1),
                pts=pts.get(name) if pts else None,
                compare_pct=None if compare_pct is None else round(compare_pct.get(name, 0.0), 1),
            )
        )
    return ExposureResult(
        key=key,
        label=label,
        lineup_count=n,
        flex=[FlexCount(position=pos, count=c, pct=round(c / flex_total * 100.0, 1) if flex_total else 0.0) for pos, c in flex.items()],
        players=players,
    )


def make_view(
    results: list[ExposureResult],
    selected: str,
    position: str,
    sort: str,
    field_label: str,
    compare_available: bool = False,
) -> ExposureView:
    """Applies the position filter and sort to the selected scope. Unknown
    `selected` falls back to the first scope."""
    chosen = next((r for r in results if r.key == selected), results[0])
    players = [p for p in chosen.players if position in ("", "ALL") or p.position == position]
    keyfn = {
        "exposure": lambda p: (-p.exposure_pct, p.name),
        "diff": lambda p: (-(p.diff if p.diff is not None else float("-inf")), p.name),
        "pts": lambda p: (-(p.pts if p.pts is not None else float("-inf")), p.name),
        "salary": lambda p: (-p.salary, p.name),
    }[sort if sort in SORTS else "exposure"]
    players.sort(key=keyfn)
    return ExposureView(
        scopes=[ExposureScope(key=r.key, label=r.label, lineup_count=r.lineup_count) for r in results],
        selected=chosen.key,
        lineup_count=chosen.lineup_count,
        flex=chosen.flex,
        players=players,
        field_label=field_label,
        has_pts=any(p.pts is not None for p in chosen.players),
        compare_available=compare_available,
    )
