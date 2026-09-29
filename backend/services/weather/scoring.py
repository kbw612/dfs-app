"""
Weather color -> Player Pool score, same 1.0-3.0 scale every other score
field uses (see backend/services/ownership/scoring.py for the analogous
Ownership formula). DST-only -- rough weather (rain/wind/snow) tends to
suppress the passing game and favor defenses/special teams, so a red or
orange weather note on a DST's own game is treated as a reason to consider
that DST a better play this week, per Kevin's own framing ("if red weather
than DST is better play").

Unlike score_ownership_pct (which returns None when there's no ownership
data to score off of at all), this function always takes a real color
string and always returns a real score -- the "no notable weather this
week" case (the common one, since WeatherSnapshot.games only ever lists
games someone actually flagged -- see backend/schemas/weather/weather.py's
own docstring) is handled one level up, the same way Game Matchup's
missing-Team-Factor case is: by simply never calling this function at all
and falling through to the flat 2.0 neutral in services/player_pool/
engine.py's _DEFAULT_SCORE_FIELDS.

Used by backend/api/player_pool/calculate_weather_scores.py, the Player
Rankings tab's Weather refresh icon.
"""

from __future__ import annotations

# Both "red" and "orange" count as severe enough to be a real DFS signal --
# per explicit "red or orange" scoping decision, rather than "red" alone.
_SEVERE_WEATHER_COLORS = {"red", "orange"}


def score_weather_color(color: str) -> float:
    """3.0 for red/orange (rough weather -- lean toward this DST), 2.0 for
    everything else (yellow/green/any other color Kevin's own vocabulary
    might introduce -- treated as "not severe enough to matter," not a
    negative signal of its own)."""
    return 3.0 if color.lower() in _SEVERE_WEATHER_COLORS else 2.0
