"""
Player Pool: merges the DK/ownership snapshot's players (see
backend/api/player_pool/latest.py for where that snapshot comes from)
with this week's manually-entered Player Pool scores (backend/
repositories/player_pool/entries_repo.py, scoped by (season, week,
platform)) plus the shared Player Defaults and Game Environment resources
into one sorted, total-scored list -- the app's replacement for the two
spreadsheets described in planning (a salary-sorted player list, and a
hand-scored "who's actually worth rostering" sheet).

compute_player_pool() does the merge; entry_total() is the "sum of
whichever score fields are actually filled in" rule that lets e.g. a QB
scored on Ownership + Volume alone still get a sensible total without
Game Environment/Matchup/Talent ever being populated for that position.

Volume and Talent are saved directly on PlayerPoolEntry, same as Game
Matchup/Ownership -- every week is independent, no carry-forward from an
earlier week. When a week has no explicit Volume/Talent save, Player Pool
falls back to that player's Player Default (backend/schemas/
player_defaults/player_defaults.py -- set in Settings' Player Default
Settings grid, one value per player per season, not tied to any specific
week), and falls back further to a neutral 2.0 if there's no Default
either. See _resolve_direct_scores and _DEFAULT_SCORE_FIELDS.

Game Matchup and Ownership don't have a per-player Default the way Volume/
Talent do -- they're expected to be re-entered fresh each week -- but a
brand new week still starts them at that same neutral 2.0 rather than
blank/unscored. An explicit save for that week always overrides this,
same as every other default/suggestion in this module.

Game Environment is different again: rather than being a plain manual
field, its *effective* value is the explicit per-player override if
there is one, otherwise whatever backend/services/game_environment/
scoring.py's formula suggests from that player's team's implied total
(pulled from the shared Game Environment data for that player's game),
otherwise a neutral 0.5 default if there's no Game Environment data for
that game yet -- 0.5, not 2.0, since Game Environment lives on its own
0.0-1.0 scale rather than the 1.0-3.0 scale every other field here uses
(see backend/schemas/player_pool/player_pool.py's docstring). See
PlayerPoolPlayer's docstring for the three related fields this produces
(game_environment/_override/_suggested).

expected_fpts is unrelated to scoring/total entirely -- it's Player
Rankings' informational "Expected FPTS" column, salary * the resolved
Salary Multiplier / 1000 (see backend/services/salary_multiplier/
engine.py), computed the same way for every position including DST.
"""

from __future__ import annotations

from pathlib import Path

from backend.repositories.game_environment.game_environment_repo import load_game_environment_for_week
from backend.repositories.player_defaults.defaults_repo import load_defaults_for_season
from backend.repositories.player_pool.entries_repo import load_entries_for_week
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.player_pool.player_pool import GameOption, PlayerPoolEntry, PlayerPoolPlayer, PlayerPoolResult
from backend.services.game_environment.scoring import score_game_environment, team_implied_total
from backend.services.ownership.position_blocks import game_key, game_label
from backend.services.salary_multiplier.engine import expected_fantasy_points

# Every score field Player Pool saves directly, except game_environment
# (handled separately -- see _resolve_game_environment) since it blends an
# override with a formula-derived suggestion rather than just starting
# blank or defaulting.
_DIRECT_SCORE_FIELDS = ["game_matchup", "ownership", "salary_value", "volume", "talent"]

# Fields that start a new week at a neutral 2.0 (the midpoint of the
# 1.0-3.0 scale) instead of blank, until explicitly scored that week --
# for Volume/Talent this is the last-resort fallback, checked only after
# that player's own Player Default (see _resolve_direct_scores); for Game
# Matchup/Ownership it's the only fallback, since they have no per-player
# Default concept. Salary Value (DST-only) deliberately isn't here -- only
# Game Environment/Matchup/Ownership/Volume/Talent default this way, per
# the explicit request that introduced this.
_DEFAULT_SCORE_FIELDS = {"game_matchup": 2.0, "ownership": 2.0, "volume": 2.0, "talent": 2.0}
# 0.5, not 2.0 -- Game Environment is on its own 0.0-1.0 scale (see
# backend/services/game_environment/scoring.py), not the 1.0-3.0 scale
# the fields above use.
_DEFAULT_GAME_ENVIRONMENT = 0.5

# Which fields actually apply to a position -- DSTs only ever use Game
# Matchup + Salary Value (no Ownership/Volume/Talent/Game Environment
# concept for a defense, per the rules this was built from). This gates
# defaulting and totaling alike: a field that isn't in a position's set
# stays None unconditionally, the same as if it were never asked about,
# rather than picking up a stray default value that would silently
# inflate that position's total without ever appearing in its UI (see
# PlayerPoolView.tsx's scoreFieldsForPosition, which this mirrors).
_DST_FIELDS = {"game_matchup", "salary_value"}
_OFFENSE_FIELDS = {"game_environment", "game_matchup", "ownership", "volume", "talent"}


def _fields_for_position(position: str) -> set[str]:
    return _DST_FIELDS if position == "DST" else _OFFENSE_FIELDS


def entry_total(scores: dict[str, float | None]) -> float:
    """Sum of every non-None score -- a player with only 2 of the 6
    fields filled in still gets a meaningful total from just those 2."""
    return sum(value for value in scores.values() if value is not None)


def _resolve_direct_scores(
    position: str, saved_entry: PlayerPoolEntry | None, player_defaults: dict[str, float | None]
) -> dict[str, float | None]:
    """This exact week's explicitly saved value if there is one; otherwise
    `player_defaults` (that player's Settings Default -- only populated
    for volume/talent, see compute_player_pool); otherwise the flat 2.0 in
    _DEFAULT_SCORE_FIELDS. Fields with neither a per-player Default nor a
    flat default (salary_value) stay None once both lookups miss, same as
    always."""
    applicable = _fields_for_position(position)
    resolved: dict[str, float | None] = {}
    for field in _DIRECT_SCORE_FIELDS:
        if field not in applicable:
            resolved[field] = None
            continue
        value = getattr(saved_entry, field) if saved_entry is not None else None
        if value is None:
            value = player_defaults.get(field)
        if value is None:
            value = _DEFAULT_SCORE_FIELDS.get(field)
        resolved[field] = value
    return resolved


def _resolve_game_environment(
    player: OwnershipPlayer, saved_entry: PlayerPoolEntry | None, game_env_entry: GameEnvironmentEntry | None
) -> tuple[float | None, float | None, float | None]:
    """(effective, override, suggested) -- see PlayerPoolPlayer's
    docstring for what each means. `suggested` always resolves to a
    number (the formula's output, or the 0.5 default when there's no
    Game Environment data yet for this game) -- there's no "no
    suggestion" state, just varying confidence in what it's based on.
    None for a position Game Environment doesn't apply to (see
    _fields_for_position) -- DSTs don't get this field at all."""
    if "game_environment" not in _fields_for_position(player.position):
        return None, None, None

    override = saved_entry.game_environment if saved_entry is not None else None
    suggested = None
    if game_env_entry is not None:
        suggested = score_game_environment(team_implied_total(game_env_entry, player.team), game_env_entry.over_under)
    if suggested is None:
        suggested = _DEFAULT_GAME_ENVIRONMENT
    effective = override if override is not None else suggested
    return effective, override, suggested


def compute_player_pool(
    players: list[OwnershipPlayer],
    season: int,
    week: int,
    platform: str,
    game_environment_dir: Path,
    nfl_data_dir: Path,
    ownership_retrieved: bool = False,
    multiplier: float = 1.0,
) -> PlayerPoolResult:
    """`ownership_retrieved` should be True whenever the caller found an
    actual Ownership snapshot for this (season, week) to merge ownership_pct
    from (see api/player_pool/latest.py), regardless of whether this
    particular player showed up in it. It's what lets a player with no
    ownership_pct be resolved to 0.0 (0% owned, retrieved-but-absent)
    instead of staying None (not retrieved at all) -- see
    PlayerPoolPlayer.ownership_pct's docstring. Defaults to False so
    existing callers/tests that don't pass it keep today's behavior
    (never backfilling).

    `multiplier` should be the already-resolved Salary Multiplier for
    this computation's platform (see backend/services/salary_multiplier/
    engine.py's resolve_multiplier -- the caller resolves it, this
    function just applies it uniformly to every row's expected_fpts).
    Defaults to 1.0 so existing callers/tests that don't pass it get a
    harmless expected_fpts = salary / 1000 rather than an error."""
    saved_entries = load_entries_for_week(nfl_data_dir, season, week, platform)
    game_env_by_key = load_game_environment_for_week(game_environment_dir, season, week)
    # Season-wide, not per-week -- a player's Default doesn't change week
    # to week the way their Player Pool entry does, so this is loaded once
    # up front rather than per player.
    defaults_by_player = load_defaults_for_season(nfl_data_dir, season)

    rows: list[PlayerPoolPlayer] = []
    game_options_by_key: dict[str, GameOption] = {}
    for player in players:
        key = game_key(player)
        game_id = "-".join(sorted(key))
        if game_id not in game_options_by_key:
            game_options_by_key[game_id] = GameOption(key=game_id, label=game_label(key))

        saved_entry = saved_entries.get(player.player)
        default_entry = defaults_by_player.get(player.player)
        player_defaults = (
            {"volume": default_entry.volume, "talent": default_entry.talent} if default_entry is not None else {}
        )
        direct_scores = _resolve_direct_scores(player.position, saved_entry, player_defaults)
        effective_env, override_env, suggested_env = _resolve_game_environment(
            player, saved_entry, game_env_by_key.get(game_id)
        )
        ownership_pct = player.ownership_pct
        if ownership_pct is None and ownership_retrieved:
            ownership_pct = 0.0

        rows.append(
            PlayerPoolPlayer(
                player=player.player,
                position=player.position,
                team=player.team,
                opponent=player.opponent,
                is_home=player.is_home,
                salary=player.salary,
                ownership_pct=ownership_pct,
                depth_rank=player.depth_rank,
                game_environment=effective_env,
                game_environment_override=override_env,
                game_environment_suggested=suggested_env,
                expected_fpts=expected_fantasy_points(player.salary, multiplier),
                total=entry_total({**direct_scores, "game_environment": effective_env}),
                **direct_scores,
            )
        )

    # Sorted by total descending overall -- the frontend groups this into
    # per-position sections (chips, same pattern as Salary Blocks), and
    # since the whole list is already total-sorted, each section comes
    # out total-sorted too without a second sort pass.
    rows.sort(key=lambda r: r.total, reverse=True)
    games = sorted(game_options_by_key.values(), key=lambda g: g.label)

    return PlayerPoolResult(
        players=rows,
        games=games,
        game_environment=list(game_env_by_key.values()),
    )
