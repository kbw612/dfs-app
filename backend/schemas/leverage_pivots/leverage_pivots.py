"""
Leverage & Pivots tab -- everything arrives finished for display (labels,
counts, groups); the frontend only renders it. See
backend/services/leverage_pivots/engine.py for the rules.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LpPlayer(BaseModel):
    player: str
    position: str
    team: str
    opponent: str
    salary: int
    ownership_pct: float


class LpRow(LpPlayer):
    """One player in a column, relative to the selected trigger."""

    salary_diff_label: str  # "(-$4,000)" / "(+$300)"
    less_label: str | None = None  # "1/9 · 89% less"; None for Correlated rows


class LpColumn(BaseModel):
    title: str
    subtitle: str
    header: str  # table header, e.g. "ATL + TB DST"
    rows: list[LpRow] = Field(default_factory=list)


class LpSelected(BaseModel):
    trigger: LpPlayer
    game_label: str  # "ATL vs TB"
    leverage: LpColumn
    correlated: LpColumn
    position_pivot: LpColumn
    pricing_pivot: LpColumn
    # Rows per position across all four columns (before the position filter).
    position_counts: list[tuple[str, int]] = Field(default_factory=list)


class LpChalkGroup(BaseModel):
    position: str
    players: list[LpPlayer] = Field(default_factory=list)


class LpReason(BaseModel):
    kind: str  # "leverage" | "position_pivot" | "pricing_pivot"
    label: str  # "Leverage" / "Position pivot" / "Pricing pivot"
    text: str  # "Chase Brown RB · 26.6% owned · $7,900"


class LpPanelPlayer(LpPlayer):
    reasons: list[LpReason]


class LpPanelGroup(BaseModel):
    reason_count: int
    players: list[LpPanelPlayer]


class LeveragePivotsResult(BaseModel):
    season: int
    week: int
    leverage_point: float
    chalk: list[LpChalkGroup] = Field(default_factory=list)
    panel: list[LpPanelGroup] = Field(default_factory=list)
    search_names: list[str] = Field(default_factory=list)
    selected: LpSelected | None = None
    # Set when `player` was given but no such player is on the slate.
    selected_not_found: bool = False
