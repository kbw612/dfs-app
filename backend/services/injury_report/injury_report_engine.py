"""
Builds an InjuryReportResult (backend/schemas/injury_report/injury_report.py)
from the latest depth-chart snapshot, this week's Schedule, and Star Players.

Deliberately reuses build_game_options (backend/services/game_logs/
game_logs_engine.py) rather than re-deriving matchup grouping/labeling from
scratch -- that function already handles the exact three things this report
needs: this week's games only, "AWAY @ HOME" labels via the shared
game_matchup module, and contest-scoped filtering (only games where both
teams are in `contest_teams`, when provided). Getting that identical
behavior for free (and any future fix to it) matters more than the report
being self-contained.

A team that build_game_options doesn't return a game for -- on a bye,
missing from the Schedule entirely, or filtered out by `contest_teams` --
simply contributes no players to the report; there's no "ungrouped" bucket,
matching the (Recommended) "exclude bye teams entirely" answer this feature
was built to.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.game_logs.game_logs import GameOption
from backend.schemas.injury_report.injury_report import InjuryGameGroup, InjuryPlayerEntry, InjuryReportResult
from backend.schemas.star_players.star_players import StarPlayersResult
from backend.services.game_logs.game_logs_engine import build_game_options
from backend.services.schedule.schedule_loader import ScheduleRow


def build_injury_report(
    snapshot: Snapshot,
    schedule_rows: list[ScheduleRow],
    week: int,
    star_players: StarPlayersResult,
    contest_teams: set[str] | None = None,
) -> InjuryReportResult:
    games: list[GameOption] = build_game_options(schedule_rows, week, contest_teams)
    game_by_team: dict[str, GameOption] = {team: g for g in games for team in g.teams}

    starred_keys = {(e.team, e.player) for e in star_players.players}

    players_by_game_key: dict[str, list[InjuryPlayerEntry]] = {g.key: [] for g in games}
    for team in snapshot.teams:
        if team.team_abbrev is None:
            continue
        game = game_by_team.get(team.team_abbrev)
        if game is None:
            # Bye week, no Schedule row yet, or filtered out by contest_teams.
            continue
        for position, players in team.positions.items():
            for depth, p in enumerate(players, start=1):
                if p.status is None:
                    continue
                players_by_game_key[game.key].append(
                    InjuryPlayerEntry(
                        team=team.team_abbrev,
                        player=p.player,
                        position=position,
                        status=p.status,
                        starred=(team.team_abbrev, p.player) in starred_keys,
                        depth=depth,
                    )
                )

    groups = [
        InjuryGameGroup(key=g.key, label=g.label, teams=g.teams, players=players_by_game_key[g.key])
        for g in games
        if players_by_game_key[g.key]
    ]

    return InjuryReportResult(scraped_at=snapshot.scraped_at, week=week, games=groups)
