"""
Team- and game-level ownership rollups for the Ownership Summary tab --
moved server-side (from the frontend's own computeTeamOwnership/
computeGameOwnership in OwnershipSummaryView.tsx) so this tab and Game
Preview's own team_projected_ownership_pct() (backend/services/
game_preview/game_preview_matchups.py) share one definition of "combined
ownership% for a team/game" instead of two independently maintained
copies -- one Python, one TypeScript -- that could silently drift apart.
Both now call ownership_totals.py's sum_current_ownership_pct() for the
"current" figure specifically.

Mirrors the frontend functions' own behavior exactly: DST is excluded from
both rollups (an explicit design decision, not an oversight -- a defense's
own ownership% isn't part of "how chalky is this team/game" the way it's
used here), a player with no ownership_pct/initial_ownership_pct yet
contributes 0 rather than being skipped (so a team/game with partial data
still shows *some* total instead of silently vanishing from the list), and
actual_total_ownership_pct comes back None -- not a real 0.0 -- whenever
`actual_by_player` is empty (no Contest Standings uploaded for this week
at all), so the tab's Actual/Actual-Diff columns can render "-" for
"we don't know yet" rather than a misleading 0%. Once Contest Standings
exist, a team/game that genuinely has 0% actual ownership across its
players still returns a real 0.0, not None -- only "no data uploaded"
triggers the None, never "the real total happens to be zero."
"""

from __future__ import annotations

from backend.schemas.ownership.ownership import OwnershipProjectionsPlayer
from backend.schemas.ownership.ownership_summary import GameOwnershipRollup, TeamOwnershipRollup
from backend.services.ownership.ownership_totals import sum_current_ownership_pct


def _game_key(team: str, opponent: str) -> str:
    return "-".join(sorted((team, opponent)))


def _game_label(team: str, opponent: str) -> str:
    return " vs ".join(sorted((team, opponent)))


def compute_team_ownership_rollups(
    players: list[OwnershipProjectionsPlayer],
    actual_by_player: dict[str, float],
) -> list[TeamOwnershipRollup]:
    """One row per team that has at least one non-DST player in `players`
    (a team appearing only via a DST row doesn't get a row at all, same as
    the frontend's own computeTeamOwnership -- its accumulation loop only
    ever creates a team entry inside the `if (p.position !== "DST")`
    branch)."""
    has_contest_data = len(actual_by_player) > 0
    teams = sorted({p.team for p in players if p.position != "DST"})
    rollups: list[TeamOwnershipRollup] = []
    for team in teams:
        team_players = [p for p in players if p.team == team and p.position != "DST"]
        initial_total = sum(p.initial_ownership_pct or 0.0 for p in team_players)
        current_total = sum_current_ownership_pct(team, players) or 0.0
        actual_total = sum(actual_by_player.get(p.player, 0.0) for p in team_players)
        rollups.append(
            TeamOwnershipRollup(
                team=team,
                initial_total_ownership_pct=initial_total,
                total_ownership_pct=current_total,
                actual_total_ownership_pct=actual_total if has_contest_data else None,
            )
        )
    return rollups


def compute_game_ownership_rollups(
    players: list[OwnershipProjectionsPlayer],
    home_by_team: dict[str, bool],
    actual_by_player: dict[str, float],
) -> list[GameOwnershipRollup]:
    """One row per (team, opponent) pair found across `players` -- unlike
    the team rollup above, a game entry is created for EVERY player
    regardless of position (so a game with only a DST row still shows up),
    since `players` on the returned row is a plain roster browse; only the
    three ownership totals themselves skip DST, same convention as the
    team rollup."""
    has_contest_data = len(actual_by_player) > 0
    by_key: dict[str, GameOwnershipRollup] = {}
    for p in players:
        key = _game_key(p.team, p.opponent)
        entry = by_key.get(key)
        if entry is None:
            entry = GameOwnershipRollup(
                key=key,
                label=_game_label(p.team, p.opponent),
                away_team=None,
                home_team=None,
                initial_total_ownership_pct=0.0,
                total_ownership_pct=0.0,
                actual_total_ownership_pct=0.0,
                players=[],
            )
            by_key[key] = entry
        entry.players.append(p)
        if p.position != "DST":
            entry.initial_total_ownership_pct += p.initial_ownership_pct or 0.0
            entry.total_ownership_pct += p.ownership_pct or 0.0
            entry.actual_total_ownership_pct = (entry.actual_total_ownership_pct or 0.0) + actual_by_player.get(
                p.player, 0.0
            )
        is_home = home_by_team.get(p.team)
        if is_home is True:
            entry.home_team = p.team
        if is_home is False:
            entry.away_team = p.team

    result = list(by_key.values())
    for entry in result:
        entry.players.sort(key=lambda pl: pl.ownership_pct if pl.ownership_pct is not None else -1.0, reverse=True)
        # Same "no Contest Standings uploaded at all" null-out as
        # compute_team_ownership_rollups -- applied after accumulation so
        # a real 0 total (Contest Standings exist, this game's players
        # just summed to zero) is left alone.
        if not has_contest_data:
            entry.actual_total_ownership_pct = None
    return result
