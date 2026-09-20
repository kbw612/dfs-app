"""
Flattens a depth-chart Snapshot into one row per (team, position,
depth_rank) for the four fantasy-relevant positions (QB/RB/WR/TE) --
built for Settings' Player Default Factors grid (see
backend/api/depth_charts/roster.py), which needs the full, all-32-teams
offense roster independent of any specific week's DK salary file. Every
other position group on the snapshot (OL, DL, LB, CB, etc.) is irrelevant
here and skipped entirely, same as a defense/special-teams group would be
if this were ever asked to cover DST too (it isn't -- see
backend/schemas/player_defaults/player_defaults.py's docstring on why
Volume/Talent/DFS Type don't apply to DST).

Unlike backend/services/ownership/depth_rank.py's build_depth_rank_lookup
(which collapses a player down to just their rank, discarding which
position group it came from, purely for name-only cross-referencing),
this keeps position and team on every row since those are exactly the
columns the grid displays -- there's no need to resolve a "two-way
player" tie-break here either, since a player only ever appears once
within a single fantasy position group's own list.
"""

from __future__ import annotations

from backend.schemas.depth_charts.roster import RosterPlayer
from backend.schemas.depth_charts.snapshot import Snapshot
from backend.services.depth_charts.scraper import extract_injury_status

_FANTASY_POSITIONS = ("QB", "RB", "WR", "TE")


def flatten_offense_roster(snapshot: Snapshot | None) -> list[RosterPlayer]:
    """Empty list if there's no depth-chart snapshot yet -- callers treat
    that the same as an empty roster, not an error (a fresh install just
    hasn't scraped depth charts yet). A team with no team_abbrev (a name
    that didn't match anything in team-info.csv -- see
    backend/services/depth_charts/enrich.py) is skipped entirely, since
    there'd be nothing to put in this row's Team column.

    Re-runs extract_injury_status on player.player (not just trusting it's
    already clean) so a snapshot scraped before a scraper fix -- e.g. the
    _INJURY_STATUS_RE hyphenated-code bug, which used to leave "(IR-R)"
    stuck on the name instead of moving it into `status` -- still displays
    a clean name here without needing to re-scrape or edit the historical
    snapshot file (those stay untouched for depth-chart diffing). A
    snapshot that already went through the fixed scraper is a safe no-op
    here (extract_injury_status on an already-clean name just returns it
    unchanged)."""
    if snapshot is None:
        return []
    roster: list[RosterPlayer] = []
    for team in snapshot.teams:
        if team.team_abbrev is None:
            continue
        for position in _FANTASY_POSITIONS:
            for i, player in enumerate(team.positions.get(position, [])):
                clean_name, _status = extract_injury_status(player.player)
                roster.append(RosterPlayer(player=clean_name, position=position, team=team.team_abbrev, depth_rank=i + 1))
    return roster
