"""
Exposure panel data, shared by the Lineup Analyzer and Contest Results tabs.
The backend returns it finished (counts, percentages, differences, filtering
and sorting); the frontend only displays it.
"""

from __future__ import annotations

from pydantic import BaseModel


class ExposurePlayer(BaseModel):
    name: str
    team: str
    position: str
    salary: int
    count: int  # lineups in the scope that roster him
    exposure_pct: float
    field_pct: float | None = None  # field ownership (projected, or the contest's %Drafted)
    diff: float | None = None  # exposure_pct - field_pct
    pts: float | None = None  # actual FPTS (Contest Results only)
    compare_pct: float | None = None  # the user's analyzed pool's exposure (Contest Results only)


class FlexCount(BaseModel):
    position: str  # RB / WR / TE
    count: int
    pct: float


class ExposureScope(BaseModel):
    key: str
    label: str
    lineup_count: int


class ExposureResult(BaseModel):
    """One scope's full data (unfiltered, unsorted) -- what gets saved."""

    key: str
    label: str
    lineup_count: int
    flex: list[FlexCount]
    players: list[ExposurePlayer]


class ExposureView(BaseModel):
    """What the endpoints return: the scope list plus the selected scope with
    the requested position filter and sort applied."""

    scopes: list[ExposureScope]
    selected: str
    lineup_count: int
    flex: list[FlexCount]
    players: list[ExposurePlayer]
    field_label: str  # column heading for field_pct
    has_pts: bool
    compare_available: bool
