"""
Resolves each uploaded-lineup player to a team by NAME -- the uploaded
lineup CSV's only per-player identifier besides a DraftKings numeric
player ID (see lineup_upload_parser.py's docstring), and this app stores
no numeric DK player ID anywhere in any schema, so name matching is the
only option here, unlike e.g. Contest Results' own lineup-to-salary
join which has the same constraint and solves it the same way.

Matches against the current week's DK salary snapshot's own player names
(backend/services/dk_salary/dk_salary_loader.py's OwnershipPlayer rows) --
that snapshot already carries every rostered player's team, including DST
rows, which use a full team name string (e.g. "Las Vegas Raiders") as
their own `player` field, the same convention the uploaded lineup CSV's
DST cells use -- so no separate team-name-to-abbreviation table is needed,
plain name matching covers both positions identically.

Uses backend/services/shared/name_match.py's normalize_player_name for
the actual comparison -- that helper is a genuinely generic lowercase/
period-strip/suffix-strip normalizer (not the stats-specific alias
lookup in the same module), so it's reused here rather than
reimplementing the same case-insensitive, whitespace-normalized
comparison from scratch.

Also resolves each player's `depth_slot` (e.g. "RB1", "WR2") by
cross-referencing the latest depth-chart snapshot via
backend/services/ownership/depth_rank.py's build_depth_rank_lookup -- the
same rank-lookup Ownership Summary already uses to label players, reused
here rather than re-deriving depth-chart ranks a third time (see
injury_report_engine.py for the other place that logic already exists,
duplicated inline there rather than reusing depth_rank.py -- deliberately
not repeating that duplication here). The depth-chart snapshot is optional
(None if nothing's been scraped yet) -- a missing snapshot just means every
resolved player's depth_slot stays None, same "partial feature still
useful" convention as every unresolved-name case below.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.lineup_scenarios.lineup_scenarios import UploadedLineup
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.ownership.depth_rank import build_depth_rank_lookup
from backend.services.shared.name_match import normalize_player_name

# Positions whose depth-chart rank is meaningful for scenario matching --
# mirrors depth_rank.py's own _OFFENSE_FANTASY_POSITIONS. DST is deliberately
# excluded: there's exactly one defense per team, so it gets the fixed slot
# "DST" (see _resolve_depth_slot) rather than a ranked one.
_DEPTH_TRACKED_POSITIONS = {"QB", "RB", "WR", "TE"}


def _resolve_depth_slot(name: str, position: str | None, depth_rank_lookup: dict[str, int]) -> str | None:
    """"RB1"/"WR2"-style depth slot for one player, or None if there's
    nothing to resolve (unresolved team/position, a position this feature
    doesn't track depth for, or no depth-chart snapshot at all)."""
    if position is None:
        return None
    if position == "DST":
        return "DST"
    if position not in _DEPTH_TRACKED_POSITIONS:
        return None
    rank = depth_rank_lookup.get(normalize_player_name(name))
    if rank is None:
        return None
    return f"{position}{rank}"


def build_team_lookup(salary_players: list[OwnershipPlayer]) -> dict[str, tuple[str, str]]:
    """{normalized player name -> (team, position)} from this week's salary
    snapshot. Position is carried alongside team so a scenario team flag's
    own `positions` filter (LineupScenarioTeamFlag.positions) can restrict
    stack-counting to e.g. just a team's RBs -- see UploadedLineupPlayer's
    own docstring for why `position` has to come from here rather than the
    uploaded CSV's `roster_position` (FLEX ambiguity). Later rows win on a
    collision (shouldn't happen in practice -- a snapshot doesn't carry the
    same player twice -- but this keeps the lookup a plain dict build
    rather than raising on a malformed file)."""
    return {normalize_player_name(p.player): (p.team, p.position) for p in salary_players}


def resolve_lineup_teams(
    lineups: list[UploadedLineup],
    salary_players: list[OwnershipPlayer],
    depth_snapshot: Snapshot | None = None,
) -> tuple[list[UploadedLineup], list[str]]:
    """Returns (lineups with `team`/`position`/`depth_slot` filled in
    wherever a name matched, deduped list of every uploaded name that
    didn't match anything in the salary snapshot). A player whose name
    doesn't resolve keeps team=None, position=None, and depth_slot=None on
    their own row -- callers (lineup_scenario_engine.py) treat that as
    "doesn't count toward any team's stack" rather than raising, same
    "partial feature still useful" convention as every other best-effort
    name-matching resolution in this app. `depth_snapshot` is optional --
    pass None (e.g. nothing scraped yet) and every player's depth_slot just
    stays None, same convention."""
    team_lookup = build_team_lookup(salary_players)
    depth_rank_lookup = build_depth_rank_lookup(depth_snapshot)

    unresolved: list[str] = []
    seen_unresolved: set[str] = set()
    resolved_lineups: list[UploadedLineup] = []
    for lineup in lineups:
        resolved_players = []
        for player in lineup.players:
            match = team_lookup.get(normalize_player_name(player.name))
            team, position = match if match is not None else (None, None)
            if match is None and player.name not in seen_unresolved:
                seen_unresolved.add(player.name)
                unresolved.append(player.name)
            depth_slot = _resolve_depth_slot(player.name, position, depth_rank_lookup)
            resolved_players.append(
                player.model_copy(update={"team": team, "position": position, "depth_slot": depth_slot})
            )
        resolved_lineups.append(lineup.model_copy(update={"players": resolved_players}))

    return resolved_lineups, unresolved
