"""
generate_diff() -- Section 2 of the design doc's `generate_diff()` pipeline
step. Compares two consecutive Snapshot objects and produces a list of
Change records: the in-memory equivalent of one changes_{timestamp}.jsonl
file. Writing that file is a separate repository concern, not this
module's job -- same split as scraper.py (parse) vs. snapshot_repo.py
(persist).

Matching key: (team_abbrev, position, player) -- players are matched by
exact name within the same team and the same position group. A player
moving positions (WR -> RB) is NOT matched across positions; it shows up
as a removal from the old position plus an addition to the new one, since
cross-position moves are rare and each Change should describe one clean
before/after state rather than infer intent across positions.

A player appears exactly once per run, even if multiple things about them
changed -- `change_types` lists every dimension that differed, in a fixed
order:
  - "status"  status field differs
  - "rank"    same status, index within the position array differs
  - "other"   added/removed player, or a team-level field
              (defensive_formation) differing between snapshots -- always
              appears alone, since it only applies when a player exists in
              just one of the two snapshots (nothing to compare status/rank
              against) or the change is team-level, not player-level.
"""

from __future__ import annotations

from backend.schemas.depth_charts.change import Change
from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team


def _team_key(team: Team) -> str:
    return team.team_abbrev or team.team_name


def _index_positions(team: Team) -> dict[str, dict[str, tuple[int, Player]]]:
    """{position: {player_name: (rank_index, Player)}} for one team."""
    return {
        position: {player.player: (i, player) for i, player in enumerate(players)}
        for position, players in team.positions.items()
    }


def _diff_team(old_team: Team, new_team: Team) -> list[Change]:
    changes: list[Change] = []
    team_abbrev = new_team.team_abbrev or old_team.team_abbrev

    old_index = _index_positions(old_team)
    new_index = _index_positions(new_team)

    for position in set(old_index) | set(new_index):
        old_players = old_index.get(position, {})
        new_players = new_index.get(position, {})

        for name in set(old_players) | set(new_players):
            old_entry = old_players.get(name)
            new_entry = new_players.get(name)

            if old_entry and new_entry:
                old_rank, old_player = old_entry
                new_rank, new_player = new_entry

                change_types: list[str] = []
                if old_player.status != new_player.status:
                    change_types.append("status")
                if old_rank != new_rank:
                    change_types.append("rank")

                if change_types:
                    changes.append(
                        Change(
                            team_abbrev=team_abbrev,
                            position=position,
                            player=name,
                            change_types=change_types,
                            previous={"status": old_player.status, "rank": old_rank + 1},
                            current={"status": new_player.status, "rank": new_rank + 1},
                        )
                    )

            elif new_entry and not old_entry:
                new_rank, new_player = new_entry
                changes.append(
                    Change(
                        team_abbrev=team_abbrev,
                        position=position,
                        player=name,
                        change_types=["other"],
                        previous=None,
                        current={"status": new_player.status, "rank": new_rank + 1},
                    )
                )

            elif old_entry and not new_entry:
                old_rank, old_player = old_entry
                changes.append(
                    Change(
                        team_abbrev=team_abbrev,
                        position=position,
                        player=name,
                        change_types=["other"],
                        previous={"status": old_player.status, "rank": old_rank + 1},
                        current=None,
                    )
                )

    if old_team.defensive_formation != new_team.defensive_formation:
        changes.append(
            Change(
                team_abbrev=team_abbrev,
                field="defensive_formation",
                change_types=["other"],
                previous=old_team.defensive_formation,
                current=new_team.defensive_formation,
            )
        )

    return changes


def generate_diff(old_snapshot: Snapshot, new_snapshot: Snapshot) -> list[Change]:
    """Compares two snapshots and returns every detected Change, across all
    teams present in both. A team appearing in only one snapshot (should
    not happen -- team_abbrev is stable, per your answer) is skipped
    rather than guessed at; there's no prior state to diff it against.
    """
    old_teams = {_team_key(t): t for t in old_snapshot.teams}
    new_teams = {_team_key(t): t for t in new_snapshot.teams}

    changes: list[Change] = []
    for team_key in sorted(set(old_teams) & set(new_teams)):
        changes.extend(_diff_team(old_teams[team_key], new_teams[team_key]))
    return changes
