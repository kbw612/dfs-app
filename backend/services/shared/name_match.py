"""
Fuzzy-ish player name normalization for cross-referencing the same player
across independently-sourced data (salary file, ownership scrape, depth
chart scrape) that don't share a player_id (see backend/schemas/
depth_charts/snapshot.py's docstring on that deferred tradeoff).

Exact-string matching breaks on two common, otherwise-harmless spelling
differences between sources:

- Initials with/without periods -- "D.J. Moore" vs "DJ Moore", "A.J. Brown"
  vs "AJ Brown".
- Generational suffixes present in one source and not the other -- "Michael
  Pittman Jr." vs "Michael Pittman", "Odell Beckham Jr" vs "Odell Beckham
  Jr.", "Melvin Gordon III" vs "Melvin Gordon".

normalize_player_name() collapses both away so callers can match on the
normalized form. It intentionally does NOT attempt anything fuzzier (no
edit-distance, no nickname tables) -- a wrong match is worse than a missed
one here, since callers (build_depth_rank_lookup and friends) already treat
"no match" as a safe, expected "rank unknown" outcome.
"""

from __future__ import annotations

import re

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_player_name(name: str) -> str:
    """Lowercased, period-stripped, trailing-suffix-stripped form of `name`
    for matching purposes only -- never for display. "D.J. Moore Jr." and
    "dj moore" both normalize to "dj moore"."""
    cleaned = name.replace(".", "").strip()
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    parts = cleaned.split(" ")
    if len(parts) > 1 and parts[-1].rstrip(",").lower() in _SUFFIXES:
        parts = parts[:-1]
    return " ".join(parts).lower()
