"""
Current Week: the single (season, week) pointer shared across every tab
that deals in weekly data (Ownership, Salary Blocks, Player Pool, and
whatever comes next) -- picked once in one shared control (see
frontend/src/App.tsx) instead of each tab keeping its own copy in
localStorage. There is exactly one of these at a time; it's not a history
of past weeks, just "what week is everyone looking at right now."

This deliberately doesn't *validate* that a (season, week) actually has
any data behind it -- a tab can still be pointed at a week nobody's
uploaded anything for yet (that's each tab's own 404/empty-state to
handle), same as season/week being freely editable today.
"""

from __future__ import annotations

from pydantic import BaseModel


class CurrentWeek(BaseModel):
    season: int
    week: int
