"""
Salary Multiplier's computed-default rule -- same "explicit override, or
else a computed default" shape as Player Selection's own resolve_selected
(see backend/services/player_selection/engine.py), just for a single
platform-scoped number instead of a per-player boolean.

expected_fantasy_points() is Player Rankings' "Expected FPTS" column
formula: multiplier * salary / 1000 (e.g. a $5,000 salary at the 4.0
DraftKings default -> 20.0 expected points). Multiplying first and
dividing once at the end is mathematically identical to dividing salary
by 1000 first and then multiplying -- (m * s) / 1000 == m * (s / 1000)
for any m, s -- so there's no "more correct" order here, this just avoids
one intermediate division.
"""

from __future__ import annotations

# DraftKings prices its salary cap on roughly a $1000-per-fantasy-point
# curve -- 4.0 is the starting assumption until someone tunes it in
# Settings. Any platform not listed here (there are none today) falls
# back to 1.0 rather than raising, so a brand-new platform name doesn't
# break Player Rankings before anyone's had a chance to set its own
# multiplier.
_DEFAULT_MULTIPLIER_BY_PLATFORM: dict[str, float] = {"DraftKings": 4.0}
_FALLBACK_MULTIPLIER = 1.0


def default_multiplier(platform: str) -> float:
    return _DEFAULT_MULTIPLIER_BY_PLATFORM.get(platform, _FALLBACK_MULTIPLIER)


def resolve_multiplier(platform: str, saved_multiplier: float | None) -> float:
    """The explicit saved override if there is one, otherwise this
    platform's computed default -- always resolves to a real number,
    there's no "no multiplier" state."""
    return saved_multiplier if saved_multiplier is not None else default_multiplier(platform)


def expected_fantasy_points(salary: int, multiplier: float) -> float:
    return multiplier * salary / 1000
