"""
Player Pool: merges the DK/ownership snapshot's players (see
backend/api/player_pool/latest.py for where that snapshot comes from)
with this week's manually-entered Player Pool scores (backend/
repositories/player_pool/entries_repo.py) plus the shared Player
Attributes and Game Environment resources into one sorted, total-scored
list -- the app's replacement for the two spreadsheets described in
planning (a salary-sorted player list, and a hand-scored "who's actually
worth rostering" sheet).

compute_player_pool() does the merge; entry_total() is the "sum of
whichever score fields are actually filled in" rule that lets e.g. a QB
scored on Ownership + Volume alone still get a sensible total without
Game Environment/Matchup/Talent ever being populated for that position.

Volume and Talent are Player Attributes (backend/repositories/
player_attributes/entries_repo.py), not Player Pool's own storage -- they
carry forward from the most recent earlier week when not explicitly
re-entered this week (see resolve_carry_forward_value) -- a player's role
or talent grade doesn't usually change week to week the way ownership or a
specific game's context does, so leaving those two blank means "still
whatever it was last time," not "unscored." They're split into their own
shared resource (rather than Player Pool's entries_repo) because they're
facts about the player, not about Player Pool specifically -- same
reasoning as Game Environment below.

Game Matchup and Ownership don't carry forward (they're expected to be
re-entered fresh each week), but a brand new week starts them at a
neutral 2.0 default rather than blank/unscored -- see
_DEFAULT_SCORE_FIELDS. An explicit save for that week always overrides
this, same as every other default/suggestion in this module.

Game Environment is different again: rather than being a plain manual
field, its *effective* value is the explicit per-player override if
there is one, otherwise whatever backend/services/game_environment/
scoring.py's formula suggests from that player's team's implied total
(pulled from the shared Game Environment data for that player's game),
otherwise the same neutral 2.0 default if there's no Game Environment
data for that game yet. See PlayerPoolPlayer's docstring for the three
related fields this produces (game_environment/_override/_suggested).
"""

from __future__ import annotations

from pathlib import Path

from backend.repositories.game_environment.game_environment_repo import load_game_environment_for_week
from backend.repositories.player_attributes.entries_repo import load_entry as load_attribute_entry
from backend.repositories.player_attributes.entries_repo import (
    resolve_carry_forward_value as resolve_attribute_carry_forward_value,
)
from backend.repositories.player_pool.entries_repo import load_entries_for_week
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.player_pool.player_pool import GameOption, PlayerPoolEntry, PlayerPoolPlayer, PlayerPoolResult
from backend.services.game_environment.scoring import score_game_environment, team_implied_total
from backend.services.ownership.position_blocks import game_key, game_label

# Every score field Player Pool saves directly, except game_environment
# (handled separately -- see _resolve_game_environment) since it blends an
# override with a formula-derived suggestion rather than just starting
# blank or defaulting. Volume/Talent aren't here at all -- see
# _resolve_attributes, which reads the shared Player Attributes resource
# instead of Player Pool's own saved_entry.
_DIRECT_SCORE_FIELDS = ["game_matchup", "ownership", "salary_value"]

_ATTRIBUTE_FIELDS = ["volume", "talent"]

# Fields that start a new week at a neutral 2.0 (the midpoint of the
# 1.0-3.0 scale) instead of blank, until explicitly scored that week --
# unlike Volume/Talent's carry-forward, this doesn't look at history at
# all, it's just "assume average" for a not-yet-evaluated player. Salary
# Value (DST-only) deliberately isn't here -- only Game Environment/
# Matchup/Ownership default this way, per the explicit request that
# introduced this.
_DEFAULT_SCORE_FIELDS = {"game_matchup": 2.0, "ownership": 2.0}
_DEFAULT_GAME_ENVIRONMENT = 2.0

# Which fields actually apply to a position -- DSTs only ever use Game
# Matchup + Salary Value (no Ownership/Volume/Talent/Game Environment
# concept for a defense, per the rules this was built from). This gates
# defaulting, carry-forward, and totaling alike: a field that isn't in a
# position's set stays None unconditionally, the same as if it were never
# asked about, rather than picking up a stray default/carry-forward value
# that would silently inflate that position's total without ever
# appearing in its UI (see PlayerPoolView.tsx's scoreFieldsForPosition,
# which this mirrors).
_DST_FIELDS = {"game_matchup", "salary_value"}
_OFFENSE_FIELDS = {"game_environment", "game_matchup", "ownership", "volume", "talent"}


def _fields_for_position(position: str) -> set[str]:
    return _DST_FIELDS if position == "DST" else _OFFENSE_FIELDS


def entry_total(scores: dict[str, float | None]) -> float:
    """Sum of every non-None score -- a player with only 2 of the 6
    fields filled in still gets a meaningful total from just those 2."""
    return sum(value for value in scores.values() if value is not None)


def _resolve_direct_scores(position: str, saved_entry: PlayerPoolEntry | None) -> dict[str, float | None]:
    applicable = _fields_for_position(position)
    resolved: dict[str, float | None] = {}
    for field in _DIRECT_SCORE_FIELDS:
        if field not in applicable:
            resolved[field] = None
            continue
        value = getattr(saved_entry, field) if saved_entry is not None else None
        if value is None and field in _DEFAULT_SCORE_FIELDS:
            value = _DEFAULT_SCORE_FIELDS[field]
        resolved[field] = value
    return resolved


def _resolve_attributes(
    player_attributes_dir: Path, season: int, week: int, player_name: str, position: str
) -> dict[str, float | None]:
    """This exact week's explicitly saved Volume/Talent if there is one,
    otherwise carried forward from the most recent earlier week in the
    shared Player Attributes resource (resolve_carry_forward_value only
    ever looks strictly *before* `week`, so the current week's own saved
    value has to be checked separately here first -- same two-step
    "this week's save, else carry-forward" shape entries_repo used to have
    inline before Volume/Talent moved to their own resource). None for
    both on a position they don't apply to (DST), same gate as every other
    field here."""
    applicable = _fields_for_position(position)
    this_week_entry = load_attribute_entry(player_attributes_dir, season, week, player_name)
    resolved: dict[str, float | None] = {}
    for field in _ATTRIBUTE_FIELDS:
        if field not in applicable:
            resolved[field] = None
            continue
        value = getattr(this_week_entry, field) if this_week_entry is not None else None
        if value is None:
            value = resolve_attribute_carry_forward_value(player_attributes_dir, season, week, player_name, field)
        resolved[field] = value
    return resolved


def _resolve_game_environment(
    player: OwnershipPlayer, saved_entry: PlayerPoolEntry | None, game_env_entry: GameEnvironmentEntry | None
) -> tuple[float | None, float | None, float | None]:
    """(effective, override, suggested) -- see PlayerPoolPlayer's
    docstring for what each means. `suggested` always resolves to a
    number (the formula's output, or the 2.0 default when there's no
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
    player_pool_dir: Path,
    game_environment_dir: Path,
    player_attributes_dir: Path,
) -> PlayerPoolResult:
    saved_entries = load_entries_for_week(player_pool_dir, season, week)
    game_env_by_key = load_game_environment_for_week(game_environment_dir, season, week)

    rows: list[PlayerPoolPlayer] = []
    game_options_by_key: dict[str, GameOption] = {}
    for player in players:
        key = game_key(player)
        game_id = "-".join(sorted(key))
        if game_id not in game_options_by_key:
            game_options_by_key[game_id] = GameOption(key=game_id, label=game_label(key))

        saved_entry = saved_entries.get(player.player)
        direct_scores = _resolve_direct_scores(player.position, saved_entry)
        attribute_scores = _resolve_attributes(player_attributes_dir, season, week, player.player, player.position)
        effective_env, override_env, suggested_env = _resolve_game_environment(
            player, saved_entry, game_env_by_key.get(game_id)
        )

        rows.append(
            PlayerPoolPlayer(
                player=player.player,
                position=player.position,
                team=player.team,
                opponent=player.opponent,
                is_home=player.is_home,
                salary=player.salary,
                ownership_pct=player.ownership_pct,
                game_environment=effective_env,
                game_environment_override=override_env,
                game_environment_suggested=suggested_env,
                total=entry_total({**direct_scores, **attribute_scores, "game_environment": effective_env}),
                **direct_scores,
                **attribute_scores,
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
