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

apply_name_alias/name_lookup_candidates take a different approach to the
same underlying problem -- rather than normalizing away suffixes
structurally, they consult Name Aliases (backend/repositories/
name_aliases/name_aliases_repo.py, edited via Settings' Name Aliases
panel), a user-curated list of "these two strings are the same player"
pairs. That's a deliberate choice for callers that need an exact,
displayable name back (e.g. to key a lookup dict) rather than just a
yes/no match -- normalize_player_name's collapsed form is match-only and
never suitable for that. Originally built for DK Players' stat-file
matching (backend/services/dk_players/dk_players_engine.py, which
re-exports both for backward compatibility), also used by Player Pool's
Player Defaults resolution (backend/services/player_pool/engine.py) for
the same suffix-drift problem between Settings' Player Default Factors
grid and whatever a given week's DK salary export spells a name as.
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


def apply_name_alias(name: str, name_aliases: dict[str, str]) -> str:
    """`name_aliases` is {alias: canonical} -- returns the canonical name
    if `name` has one, otherwise `name` unchanged."""
    return name_aliases.get(name, name)


def name_lookup_candidates(name: str, name_aliases: dict[str, str]) -> list[str]:
    """Every spelling worth trying for `name` when matching against an
    external source (a stat file, Contest Standings, this week's DK salary
    export, ...), in the order to try them: `name` itself first, since
    independently-maintained name lists commonly agree with each other and
    need no translation at all -- only a genuine mismatch needs an alias.
    Then the forward alias->canonical mapping (if `name` IS a known
    alias), for the source that needs the "other" spelling. Then the
    *reverse* mapping (if `name` IS a known canonical, whichever alias
    maps to it), since which direction an alias needs to be applied can
    differ per source -- one source might already agree with `name`'s own
    spelling (no translation needed there) while another needs the
    canonical or alias spelling instead, and there's no way to know which
    up front. Callers try these in order and stop at the first match, so a
    name that matches natively never gets needlessly translated."""
    candidates = [name]
    canonical = name_aliases.get(name)
    if canonical is not None and canonical not in candidates:
        candidates.append(canonical)
    for alias, canon in name_aliases.items():
        if canon == name and alias not in candidates:
            candidates.append(alias)
    return candidates
