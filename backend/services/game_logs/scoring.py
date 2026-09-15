"""
Small pure-math helpers shared by Game Logs (game_logs_engine.py) and Game
Logs Against (game_logs_against_engine.py) -- both tabs compute the same
Multiplier (FPTS per $1000 of salary) and Non_TD/TD percentage-of-FPTS
figures from a DK Players tracker row, just over a different set of rows
(one team's own roster history vs. every opposing player who faced a given
team). Pulled out here once a second caller needed them, rather than
duplicating -- see backend/services/game_logs/game_logs_engine.py's own
prior history for the original single-caller versions of these.
"""

from __future__ import annotations


def multiplier(fpts: float, salary: int) -> float | None:
    """None when salary is 0 (a bad/placeholder salary row) -- dividing by
    zero-thousand dollars isn't a meaningful multiplier."""
    if salary <= 0:
        return None
    return fpts / (salary / 1000)


def pct_of_total(part: float, total: float) -> float | None:
    """None when total is 0 -- "what % of 0 FPTS was this part" has no
    sensible answer, so callers render "-" rather than a divide-by-zero
    0.0/undefined result."""
    if total == 0:
        return None
    return part / total * 100
