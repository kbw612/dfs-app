"""
Salary Multiplier: a per-platform number Player Rankings uses for its own
"Expected FPTS" column (formula: multiplier * salary / 1000 -- see
backend/services/salary_multiplier/engine.py). Scoped to platform alone,
not season or week -- it's a property of that platform's salary scale
(DraftKings prices roughly on a $1000-per-fantasy-point curve, hence the
4.0 default), not something that changes week to week the way Player
Pool's own scores do.

SalaryMultiplierEntry.multiplier is the explicit override only -- None
means "no override saved," not "zero." See engine.py's resolve_multiplier
for how that falls back to a computed per-platform default instead of
leaving Expected FPTS blank. SalaryMultiplierResult is the read side:
`multiplier` is always the resolved number (never None), `override` is
the raw saved value so Settings' input can tell "explicitly set to the
same number as the default" apart from "never touched."
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SalaryMultiplierEntry(BaseModel):
    platform: str
    multiplier: Optional[float] = None


class SalaryMultiplierResult(BaseModel):
    platform: str
    multiplier: float
    override: Optional[float] = None
