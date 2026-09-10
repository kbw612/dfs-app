"""
Cross-references ownership players against the latest depth-chart snapshot
to fill in each player's DFS role label (position + depth-chart rank, e.g.
"RB1") for display -- see OwnershipPlayer.depth_rank's docstring. Matching is by
player name alone, the same "no player_id yet" tradeoff already documented
in backend/schemas/depth_charts/snapshot.py -- a name that doesn't appear on
any team's depth chart (a typo, a practice-squad call-up not yet reflected
there, or a genuine mismatch between the two independently-scraped data
sources) just gets no rank rather than a wrong one. Names are compared via
normalize_player_name() (periods and Jr/Sr/II/III/IV suffixes stripped) so
"D.J. Moore" on one side and "DJ Moore" on the other, or "Michael Pittman
Jr." vs "Michael Pittman", still match.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot, Team
from backend.services.shared.name_match import normalize_player_name

# Mirrors usage_bump/engine.py's _build_location tie-break: if the same
# name is listed under more than one position group on a team (a two-way
# player, e.g. a WR who's also a punt returner), whichever listing is an
# offensive fantasy position wins, since that's the listing DFS
# salary/ownership data actually cares about.
_OFFENSE_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}


def _team_ranks(team: Team) -> dict[str, int]:
    """Normalized player name -> 1-indexed rank within their position
    group, for one team."""
    ranks: dict[str, int] = {}
    ordered_positions = sorted(
        team.positions.items(), key=lambda item: item[0] not in _OFFENSE_FANTASY_POSITIONS
    )
    for _position, players in ordered_positions:
        for i, player in enumerate(players):
            ranks.setdefault(normalize_player_name(player.player), i + 1)
    return ranks


def build_depth_rank_lookup(depth_snapshot: Snapshot | None) -> dict[str, int]:
    """Normalized player name -> depth-chart rank, across every team in the
    snapshot. Empty if there's no depth-chart snapshot yet (a fresh install
    that hasn't scraped depth charts at all) -- callers should treat a
    missing lookup entry as "rank unknown", not an error. Callers must look
    up with normalize_player_name(query_name), not the raw name, since keys
    here are normalized."""
    if depth_snapshot is None:
        return {}
    lookup: dict[str, int] = {}
    for team in depth_snapshot.teams:
        for name, rank in _team_ranks(team).items():
            lookup.setdefault(name, rank)
    return lookup
