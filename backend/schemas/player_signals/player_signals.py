"""Schemas for the Player Pool Signals tab (see services/player_signals/engine.py)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SignalChip(BaseModel):
    family: Literal["usage", "matchup", "game", "role", "price"]
    # "up" is a reason to play him, "down" a reason against; net = ups - downs.
    polarity: Literal["up", "down"]
    text: str
    # Hover list: the games/players behind the chip, e.g. "Kyren Williams W3 (121 yds, TD)".
    detail: list[str] = Field(default_factory=list)


class SignalPlayer(BaseModel):
    player: str
    position: str
    team: str
    opponent: str
    salary: int
    ownership_pct: Optional[float] = None
    status: Optional[str] = None
    pts_last_x: Optional[float] = None
    games_used: int = 0
    up: int = 0
    down: int = 0
    net: int = 0
    signals: list[SignalChip] = Field(default_factory=list)


class ThresholdInfo(BaseModel):
    key: str
    label: str
    group: str
    value: float
    default: float


class PlayerSignalsResult(BaseModel):
    season: int
    week: int
    last_weeks: int
    min_net: int
    opponent_scope: str = "last"
    ownership_missing: bool = False
    first_week: int
    through_week: int
    total_players: int
    players: list[SignalPlayer]
    thresholds: list[ThresholdInfo]
