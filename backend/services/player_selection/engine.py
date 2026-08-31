"""
Player Selection's default-selection rule plus the shared filter applied
by both Player Pool (backend/api/player_pool/latest.py) and Salary Blocks
(backend/api/ownership/position_blocks.py) -- see
backend/schemas/player_selection/player_selection.py for the feature's
overall shape.

A player is selected by default unless their position has a minimum
salary threshold (_MIN_SALARY_BY_POSITION) and their salary falls under
it -- these are exactly the cheap, unlikely-to-be-rostered players Settings
starts you off excluding, so narrowing the pool from there is mostly
unchecking a handful of chalk plays rather than building the whole list up
from nothing. Positions with no threshold (DST) are always selected by
this function -- but see filter_selected_players below, which skips DST
entirely rather than relying on that.
"""

from __future__ import annotations

from typing import Protocol

_MIN_SALARY_BY_POSITION: dict[str, int] = {
    "QB": 5000,
    "RB": 5000,
    "WR": 4000,
    "TE": 3000,
}


class _SelectablePlayer(Protocol):
    player: str
    position: str
    salary: int


def default_selected(position: str, salary: int) -> bool:
    threshold = _MIN_SALARY_BY_POSITION.get(position)
    if threshold is None:
        return True
    return salary >= threshold


def resolve_selected(player: str, position: str, salary: int, overrides: dict[str, bool]) -> bool:
    """An explicit override (any prior checkbox toggle -- see
    player_selection_repo.py) always wins; otherwise falls back to the
    computed default above."""
    if player in overrides:
        return overrides[player]
    return default_selected(position, salary)


def filter_selected_players(players: list[_SelectablePlayer], overrides: dict[str, bool]) -> list[_SelectablePlayer]:
    """Drops every QB/RB/WR/TE that resolves to unselected -- DST always
    passes through untouched, this feature doesn't apply to it (see this
    module's docstring)."""
    return [p for p in players if p.position == "DST" or resolve_selected(p.player, p.position, p.salary, overrides)]
