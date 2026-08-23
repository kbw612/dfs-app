"""
compute_usage_bumps() -- derived analysis over a single depth-chart
snapshot (not a diff between two runs, unlike diff.py). Every player with a
non-null status (all 11 status codes count, not just injury ones) is a
"trigger" -- a potential source of opportunity for other players on the
same team.

Each trigger's usage-bump list -- who benefits from *their* injury -- is
resolved one of two ways, in priority order:

1. Curated (config/usage-bump-players.json, usage_bump_players_repo.py):
   if the trigger has an explicit named-beneficiary list for their team,
   that list is used, in order.
2. Default position-based (config/usage-bump-position-settings.json,
   position_settings_repo.py): otherwise, the trigger's role label (their
   position + real depth-chart rank, e.g. "RB1") is looked up in a
   universal (not per-team) table of role -> beneficiary-role lists (e.g.
   "RB1" -> ["RB2", "RB3", "WR1", "WR2", "TE1", "WR3"]). Each beneficiary
   role label is resolved to an actual player via *this* team's real depth
   chart. A trigger whose role has no entry here (and no curated override)
   has no usage-bump list at all -- their injury produces zero bump for
   anyone. There is no third, generic fallback.

Either way, the resulting list is truncated to at most 5 names (unresolved
or off-roster names are dropped first, preserving order, before the cap is
applied) -- this app's scoring matrix only covers list positions 1-5.

Scoring (config/player-out-settings.json, scoring_matrix_repo.py): the
trigger itself is always out by definition and is never a scorable target.
For the *rest* of the list, we check every member's current status --
they can be out too -- and look up the exact matching combination of
"also-out" list positions (1-indexed) in the matrix; `(0,)` is the
sentinel key for "nobody else in the list is out." Whatever the matching
row says gets applied to each list member who's currently healthy. If no
row matches a given combination, that trigger contributes nothing (no
partial-credit fallback).

A beneficiary who shows up in more than one active trigger's list (e.g.
named directly in one player's curated list while also being close enough
in a different position's default list) gets every contribution added
together. Only players with a final bump_score > 0 appear in the result.

Every player/rank display anywhere in this module (UsageBump.position,
UsageBumpCause.position, UsageBumpListEntry.position, etc.) goes
through _build_location, which prefers a player's offensive fantasy
listing (QB/RB/WR/TE) whenever the same name appears under more than one
position group on the same team (a real two-way player, e.g. a CB who's
also a WR, or a WR who's also listed as a punt returner) -- otherwise
whichever group happened to iterate last would silently win and mislabel
that player everywhere, even though role-label resolution itself always
matches the intended group correctly.

Each UsageBumpCause also carries the full context behind its weight --
its own `position`/`rank` (the trigger's real role label, e.g. "WR2");
`player_out_depths` (the exact combo key looked up in the matrix, named
to match player-out-settings.json's own field); `usage_bump_list` (the
trigger's whole resolved list, with the matched row's weight, each
member's own position, and their current status, applied to every
position in it -- not just the position this particular beneficiary
occupies); and `source`/`source_role_label`/`source_role_positions` (which
of the two config files resolved this trigger's list, and if it was the
position-settings fallback, the exact role label and raw usageBumpPositions
list that were looked up) -- so the frontend can render the literal
config/scoring-matrix data that produced the number, not just the number
itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.schemas.depth_charts.snapshot import Snapshot, Team
from backend.schemas.usage_bump.usage_bump import UsageBump, UsageBumpCause, UsageBumpListEntry

_ROLE_LABEL_RE = re.compile(r"^([A-Za-z]+)(\d+)$")

# When a player is listed under more than one position group on the same
# team's depth chart -- a real two-way player (e.g. a WR who also plays
# CB), or a WR/RB who's also listed as a punt/kick returner -- their
# offensive fantasy listing (QB/RB/WR/TE) is what this whole feature cares
# about, so it should win over any other listing for the same name. See
# _build_location.
_OFFENSE_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}


@dataclass
class _ResolvedUsageBumpList:
    """What _usage_bump_list found, plus which of the two config files it
    came from -- carried through to UsageBumpCause.source/source_role_*
    so the frontend can show *why* this list looks the way it does, not
    just the list itself."""

    names: list[str]
    source: str  # "curated" or "position-settings"
    role_label: str | None = None  # only set when source == "position-settings"
    role_positions: list[str] | None = None  # ditto -- the raw (unresolved) role labels


def _build_location(team: Team) -> dict[str, tuple[str, int]]:
    """Player name -> (position, 1-indexed rank within that position
    group), for every player on this team. If a name shows up under more
    than one position group, whichever listing is an offensive fantasy
    position (QB/RB/WR/TE) wins -- processed first, and `setdefault` means
    a later, non-fantasy listing for the same name can never overwrite it.
    Without this, a two-way player's WR listing (which is what
    _resolve_role_label actually matched against) could get silently
    clobbered by their CB or punt-returner listing elsewhere in the same
    team.positions dict, showing the wrong role label everywhere this
    lookup is used (UsageBump.position/rank, UsageBumpListEntry)."""
    location: dict[str, tuple[str, int]] = {}
    ordered_positions = sorted(
        team.positions.items(), key=lambda item: item[0] not in _OFFENSE_FANTASY_POSITIONS
    )
    for position, players in ordered_positions:
        for i, player in enumerate(players):
            location.setdefault(player.player, (position, i + 1))
    return location


def _resolve_role_label(label: str, team: Team) -> str | None:
    """"WR1" -> whoever's real rank-1 WR is on this team, or None if the
    label is malformed or this team doesn't have a player at that slot."""
    match = _ROLE_LABEL_RE.match(label)
    if not match:
        return None
    position, rank = match.group(1), int(match.group(2))
    players = team.positions.get(position, [])
    if 1 <= rank <= len(players):
        return players[rank - 1].player
    return None


def _usage_bump_list(
    trigger_name: str,
    trigger_team_abbrev: str,
    trigger_position: str,
    trigger_rank: int,
    team: Team,
    usage_bump_players: dict[tuple[str, str], list[str]],
    position_settings: dict[str, list[str]],
    location: dict[str, tuple[str, int]],
) -> _ResolvedUsageBumpList:
    """Up to 5 real player names who could benefit from this trigger being
    out, plus which config file resolved them. `names` is empty if the
    trigger has no usage-bump list at all (no curated entry, no
    default-position entry)."""
    curated = usage_bump_players.get((trigger_team_abbrev, trigger_name))
    if curated is not None:
        names = curated
        source, role_label, role_positions = "curated", None, None
    else:
        role_label = f"{trigger_position}{trigger_rank}"
        role_list = position_settings.get(role_label)
        if role_list is None:
            return _ResolvedUsageBumpList(names=[], source="position-settings")
        names = [
            resolved
            for resolved in (_resolve_role_label(label, team) for label in role_list)
            if resolved is not None
        ]
        source, role_positions = "position-settings", role_list

    # Drop names that aren't actually on this team's current depth chart
    # (stale curated entries, or a resolved role slot that doesn't apply
    # here) before applying the 5-position cap, so the cap always lands on
    # 5 *usable* names rather than wasting slots on dead entries.
    usable_names = [name for name in names if name in location][:5]
    return _ResolvedUsageBumpList(
        names=usable_names, source=source, role_label=role_label, role_positions=role_positions
    )


def _score_usage_bump_list(
    trigger_name: str,
    trigger_status: str,
    trigger_position: str,
    trigger_rank: int,
    resolved: _ResolvedUsageBumpList,
    status_by_name: dict[str, str | None],
    location: dict[str, tuple[str, int]],
    matrix: dict[tuple[int, ...], dict[int, float]],
) -> dict[str, UsageBumpCause]:
    """This one trigger's contribution to each currently-healthy member of
    its own usage-bump list. Empty if the exact combination of who-else
    is-out among the list has no matching row in the scoring matrix."""
    usage_bump_names = resolved.names
    out_positions = tuple(
        sorted(
            i + 1 for i, name in enumerate(usage_bump_names) if status_by_name.get(name) is not None
        )
    )
    player_out_depths = out_positions if out_positions else (0,)
    row = matrix.get(player_out_depths)
    if row is None:
        return {}

    # Shared across every cause produced by this call -- the full matched
    # row applied to the full list, so the frontend can show "here's the
    # whole scoring-matrix row that was used" for any beneficiary in it,
    # not just the one weight that mattered for them.
    usage_bump_list = [
        UsageBumpListEntry(
            depth=i + 1,
            player=name,
            position=location[name][0],
            rank=location[name][1],
            status=status_by_name.get(name),
            weight=row.get(i + 1, 0),
        )
        for i, name in enumerate(usage_bump_names)
    ]

    contributions: dict[str, UsageBumpCause] = {}
    for i, name in enumerate(usage_bump_names):
        if status_by_name.get(name) is not None:
            continue  # this list member is out too -- no credit
        weight = row.get(i + 1, 0)
        if weight:
            contributions[name] = UsageBumpCause(
                player=trigger_name,
                status=trigger_status,
                position=trigger_position,
                rank=trigger_rank,
                weight=weight,
                player_out_depths=list(player_out_depths),
                usage_bump_list=usage_bump_list,
                source=resolved.source,
                source_role_label=resolved.role_label,
                source_role_positions=resolved.role_positions,
            )
    return contributions


def _team_usage_bumps(
    team: Team,
    usage_bump_players: dict[tuple[str, str], list[str]],
    position_settings: dict[str, list[str]],
    matrix: dict[tuple[int, ...], dict[int, float]],
) -> list[UsageBump]:
    team_abbrev = team.team_abbrev or ""

    location = _build_location(team)
    status_by_name: dict[str, str | None] = {
        player.player: player.status for players in team.positions.values() for player in players
    }

    scores: dict[str, float] = {}
    causes: dict[str, list[UsageBumpCause]] = {}

    for position, players in team.positions.items():
        for i, player in enumerate(players):
            if player.status is None:
                continue  # not a trigger

            resolved = _usage_bump_list(
                player.player,
                team_abbrev,
                position,
                i + 1,
                team,
                usage_bump_players,
                position_settings,
                location,
            )
            if not resolved.names:
                continue

            for beneficiary, cause in _score_usage_bump_list(
                player.player, player.status, position, i + 1, resolved, status_by_name, location, matrix
            ).items():
                scores[beneficiary] = scores.get(beneficiary, 0) + cause.weight
                causes.setdefault(beneficiary, []).append(cause)

    return [
        UsageBump(
            team_abbrev=team.team_abbrev,
            position=location[name][0],
            player=name,
            rank=location[name][1],
            bump_score=score,
            causes=causes[name],
        )
        for name, score in scores.items()
        if score > 0
    ]


def compute_usage_bumps(
    snapshot: Snapshot,
    usage_bump_players: dict[tuple[str, str], list[str]],
    position_settings: dict[str, list[str]],
    matrix: dict[tuple[int, ...], dict[int, float]],
) -> list[UsageBump]:
    """Every usage bump across every team, sorted by bump_score
    descending (ties broken by team, then position, then rank -- the
    frontend re-sorts client-side per its active sort control anyway).
    """
    usage_bumps: list[UsageBump] = []
    for team in snapshot.teams:
        usage_bumps.extend(_team_usage_bumps(team, usage_bump_players, position_settings, matrix))

    usage_bumps.sort(key=lambda o: (-o.bump_score, o.team_abbrev or "", o.position, o.rank))
    return usage_bumps
