"""Lineup flags: irregularities the Lineup Analyzer marks on a lineup. They
only mark -- nothing is blocked or removed. See
backend/services/lineup_analyzer/flags.py for the rules."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FlagSettings(BaseModel):
    """Thresholds for the flags that have one (all editable on the tab)."""

    low_total: float = Field(40.0, ge=0)  # game total below this is a note
    underdog_spread: float = Field(7.0, ge=0)  # RB/DST on a team underdog by this much
    punt_salary: int = Field(3500, ge=0)  # skill player priced at or below this is a punt
    punt_count: int = Field(3, ge=1)  # this many punts flags the lineup
    own_slice_pct: float = Field(10.0, ge=0, le=50)  # top/bottom slice of the pool by total ownership


class LineupFlag(BaseModel):
    code: str
    severity: str  # "error" | "warning" | "note"
    label: str
    text: str


class FlagSummary(BaseModel):
    code: str
    severity: str
    label: str
    count: int  # lineups with this flag
