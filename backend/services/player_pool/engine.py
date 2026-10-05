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

Player Defaults are looked up by player name, but Settings' grid and this
week's DK salary export are independently maintained and can disagree on
a generational suffix ("Brian Thomas" saved in Settings vs. this week's
salary file spelling it "Brian Thomas Jr.") -- exact-string matching alone
would silently drop back to the neutral 2.0 default for a player who
actually has a real, curated Default, with no error to say so. Name
Aliases (same mechanism DK Players' stat-file matching uses, see
backend/services/shared/name_match.py's name_lookup_candidates) resolves
this: see _resolve_direct_scores' `name_aliases` param and
compute_player_pool's own `name_aliases_json`.

Ownership doesn't have any kind of Default -- it's expected to be
re-entered fresh each week -- but a brand new week still starts it at
that same neutral 2.0 rather than blank/unscored. An explicit save for
that week always overrides this, same as every other default/suggestion
in this module.

Game Matchup is different: it has no *per-player* Default the way Volume/
Talent do, but it does have a per-(team, position) one -- Team Default
Factors (backend/schemas/team_factors/team_factors.py, set in Settings'
Team Default Factors grid). A player's Matchup for a week with no
explicit save of its own starts from *their opponent's* Team Default
Factor at the player's own position (see _resolve_team_factor_defaults),
falling back further to the same neutral 2.0 if that opponent/position
pair has never been set either, or if the player's opponent isn't known
yet (no Schedule/salary data for this week). An explicit per-week save
always wins over this, same as every other field here.

Game Environment is different again: rather than being a plain manual
field, its *effective* value is the explicit per-player override if
there is one, otherwise whatever backend/services/game_environment/
scoring.py's formula suggests from that player's team's implied total
(pulled from the shared Game Environment data for that player's game),
otherwise a neutral 2.0 default if there's no Game Environment data for
that game yet -- the same 1.0-3.0 scale and same neutral midpoint every
other field here uses (see backend/schemas/player_pool/player_pool.py's
docstring; Game Environment used to live on its own smaller 0.0-1.0
scale, but that's no longer the case). See PlayerPoolPlayer's docstring
for the three related fields this produces
(game_environment/_override/_suggested).

expected_fpts is unrelated to scoring/total entirely -- it's Player
Rankings' informational "Expected FPTS" column, salary * the resolved
Salary Multiplier / 1000 (see backend/services/salary_multiplier/
engine.py), computed the same way for every position including DST.
"""

from __future__ import annotations

from pathlib import Path

from backend.repositories.game_environment.game_environment_repo import load_game_environment_for_week
from backend.repositories.name_aliases.name_aliases_repo import load_name_aliases
from backend.repositories.player_defaults.defaults_repo import load_defaults_for_season
from backend.repositories.player_pool.entries_repo import load_entries_for_week
from backend.repositories.team_factors.team_factors_repo import load_factors_for_season
from backend.repositories.weather.weather_repo import load_weather
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.player_pool.player_pool import GameOption, PlayerPoolEntry, PlayerPoolPlayer, PlayerPoolResult
from backend.schemas.team_factors.team_factors import TeamFactorEntry
from backend.schemas.weather.weather import WeatherGame
from backend.services.game_environment.scoring import score_game_environment, team_implied_total
from backend.services.ownership.position_blocks import game_key, game_label
from backend.services.salary_multiplier.engine import expected_fantasy_points
from backend.services.shared.name_match import name_lookup_candidates
from backend.services.weather.scoring import score_weather_color

# Every score field Player Pool saves directly, except game_environment
# (handled separately -- see _resolve_game_environment) since it blends an
# override with a formula-derived suggestion rather than just starting
# blank or defaulting.
_DIRECT_SCORE_FIELDS = ["game_matchup", "ownership", "salary_value", "weather", "volume", "talent"]

# Fields that start a new week at a neutral 2.0 (the midpoint of the
# 1.0-3.0 scale) instead of blank, until explicitly scored that week --
# for Volume/Talent this is the last-resort fallback, checked only after
# that player's own Player Default (see _resolve_direct_scores); for Game
# Matchup/Ownership/Salary Value/Weather it's the only fallback, since they
# have no per-player Default concept. Every _DIRECT_SCORE_FIELDS entry
# defaults this way now (Salary Value used to be a deliberate exception,
# staying blank until explicitly scored -- that's no longer the case).
_DEFAULT_SCORE_FIELDS = {
    "game_matchup": 2.0,
    "ownership": 2.0,
    "volume": 2.0,
    "talent": 2.0,
    "salary_value": 2.0,
    "weather": 2.0,
}
# Same neutral 2.0 midpoint as the fields above -- Game Environment used
# to live on its own 0.0-1.0 scale (0.5 default) but now shares the
# 1.0-3.0 scale every other field uses (see backend/services/
# game_environment/scoring.py), so its default matches too. Kept as its
# own constant (rather than folded into _DEFAULT_SCORE_FIELDS) since it's
# resolved through a different path -- see _resolve_game_environment.
_DEFAULT_GAME_ENVIRONMENT = 2.0

# Which fields actually apply to a position -- DSTs use Game Matchup,
# Ownership, Salary Value, and Weather (no Volume/Talent/Game Environment
# concept for a defense, per the rules this was built from; Weather is
# DST-only too -- rough weather is a defense/special-teams signal, not an
# offensive-skill-position one, per how this was scoped). Ownership uses
# its own DST-specific breakpoints (see backend/services/ownership/
# scoring.py's score_dst_ownership_pct) even though it shares the same
# `ownership` field/column as offense. This gates defaulting and totaling
# alike: a field that isn't in a position's set stays None unconditionally,
# the same as if it were never asked about, rather than picking up a stray
# default value that would silently inflate that position's total without
# ever appearing in its UI (see PlayerPoolView.tsx's
# scoreFieldsForPosition, which this mirrors).
_DST_FIELDS = {"game_matchup", "ownership", "salary_value", "weather"}
_OFFENSE_FIELDS = {"game_environment", "game_matchup", "ownership", "volume", "talent", "standalone"}


def _fields_for_position(position: str) -> set[str]:
    return _DST_FIELDS if position == "DST" else _OFFENSE_FIELDS


def entry_total(scores: dict[str, float | None]) -> float:
    """Sum of every non-None score -- a player with only 2 of the 6
    fields filled in still gets a meaningful total from just those 2."""
    return sum(value for value in scores.values() if value is not None)


def _resolve_player_defaults(
    player_name: str, defaults_by_player: dict[str, object], name_aliases: dict[str, str]
) -> dict[str, float | None]:
    """Alias-aware, per-field merge across every name_lookup_candidates
    spelling of `player_name` -- not just a single winning entry. This
    matters for real, messy Settings data: a suffix-mismatch cleanup can
    leave a stub Default behind under the "new" spelling (e.g. "Brian
    Thomas Jr." saved with dfs_type set but volume/talent never filled
    in) alongside the original, fully-scored entry under the old spelling
    ("Brian Thomas"). Picking whichever single entry matches `player_name`
    first would lock in that stub's blank fields and never fall through to
    the real values sitting under the alias -- merging field-by-field (own
    spelling's value if set, else the first alias candidate's) gets the
    real Volume/Talent regardless of which spelling happens to hold them."""
    merged: dict[str, float | None] = {"volume": None, "talent": None}
    for candidate in name_lookup_candidates(player_name, name_aliases):
        entry = defaults_by_player.get(candidate)
        if entry is None:
            continue
        if merged["volume"] is None and entry.volume is not None:
            merged["volume"] = entry.volume
        if merged["talent"] is None and entry.talent is not None:
            merged["talent"] = entry.talent
    return merged


def _resolve_default_standalone(
    player_name: str, defaults_by_player: dict[str, object], name_aliases: dict[str, str]
) -> bool:
    """Whether any of `player_name`'s own Settings Default entries (own
    spelling or any name_lookup_candidates alias, same alias-aware merge
    _resolve_player_defaults uses for volume/talent) has "Standalone" in
    its dfs_types -- False if there's no Default at all, or none of them
    carry that tag. Unlike volume/talent's None-means-"keep checking the
    next fallback" merge, this is a plain boolean: True as soon as any
    candidate spelling has the tag, since there's no further fallback
    after this (see _resolve_standalone)."""
    for candidate in name_lookup_candidates(player_name, name_aliases):
        entry = defaults_by_player.get(candidate)
        if entry is not None and "Standalone" in entry.dfs_types:
            return True
    return False


def _resolve_standalone(
    position: str, saved_entry: PlayerPoolEntry | None, default_standalone: bool
) -> bool | None:
    """This exact week's explicit save if there is one, otherwise
    `default_standalone` (see _resolve_default_standalone) -- None
    unconditionally for DST, same "doesn't apply to this position"
    convention _resolve_direct_scores uses for volume/talent (see
    _fields_for_position). Deliberately kept separate from
    _resolve_direct_scores/_DIRECT_SCORE_FIELDS: this is a boolean flag,
    not a 1.0-3.0 judgment-call score, and must never be summed into
    entry_total()."""
    if "standalone" not in _fields_for_position(position):
        return None
    if saved_entry is not None and saved_entry.standalone is not None:
        return saved_entry.standalone
    return default_standalone


def _resolve_direct_scores(
    position: str, saved_entry: PlayerPoolEntry | None, player_defaults: dict[str, float | None]
) -> dict[str, float | None]:
    """This exact week's explicitly saved value if there is one; otherwise
    `player_defaults` (volume/talent come from that player's own Settings
    Default, game_matchup comes from their opponent's Team Default
    Factor at this position -- see compute_player_pool, which populates
    both before calling this); otherwise the flat 2.0 in
    _DEFAULT_SCORE_FIELDS -- every _DIRECT_SCORE_FIELDS entry has one now,
    so a field only stays None here when it doesn't apply to `position` at
    all (see _fields_for_position)."""
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


def _resolve_team_factor_default(
    opponent: str | None, position: str, team_factors_by_key: dict[tuple[str, str], TeamFactorEntry]
) -> float | None:
    """The suggested Matchup value for a player at `position` facing
    `opponent` this week -- that opponent's own Team Default Factor at
    this position, or None if it's never been set (or `opponent` isn't
    known yet, e.g. no Schedule data for this week). None here just means
    _resolve_direct_scores' own generic fallback chain continues on to
    the flat 2.0 in _DEFAULT_SCORE_FIELDS, same as a player with no
    Player Default at all falls through for Volume/Talent."""
    if opponent is None:
        return None
    entry = team_factors_by_key.get((opponent, position))
    return entry.factor if entry is not None else None


def _resolve_weather_default(
    game_id: str, weather_by_key: dict[str, WeatherGame]
) -> float | None:
    """The suggested Weather value for whichever game `game_id` names --
    score_weather_color() applied to that game's own Weather note, or None
    if this game has no notable-weather note at all this week (the common
    case -- see WeatherGame's own docstring: only games someone actually
    flagged appear here). None here just means _resolve_direct_scores' own
    generic fallback chain continues on to the flat 2.0 in
    _DEFAULT_SCORE_FIELDS, same as a game with no Team Default Factor set
    falls through for Game Matchup."""
    game = weather_by_key.get(game_id)
    if game is None:
        return None
    return score_weather_color(game.color)


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
    platform: str,
    game_environment_dir: Path,
    nfl_data_dir: Path,
    ownership_retrieved: bool = False,
    multiplier: float = 1.0,
    name_aliases_json: Path | None = None,
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
    harmless expected_fpts = salary / 1000 rather than an error.

    `name_aliases_json` should be settings.name_aliases_json in real
    callers -- see _resolve_player_defaults. Defaults to None (no aliases
    applied, plain exact-name lookup) so existing callers/tests that don't
    pass it keep today's behavior."""
    saved_entries = load_entries_for_week(nfl_data_dir, season, week, platform)
    game_env_by_key = load_game_environment_for_week(game_environment_dir, season, week)
    # Season-wide, not per-week -- a player's Default doesn't change week
    # to week the way their Player Pool entry does, so this is loaded once
    # up front rather than per player. Same reasoning for team factors
    # (Team Default Factors, keyed by (team, position) instead of player).
    defaults_by_player = load_defaults_for_season(nfl_data_dir, season)
    team_factors_by_key = load_factors_for_season(nfl_data_dir, season)
    weather = load_weather(nfl_data_dir, season, week)
    weather_by_key: dict[str, WeatherGame] = {g.game_key: g for g in weather.games} if weather is not None else {}
    name_aliases = (
        {alias.alias: alias.canonical for alias in load_name_aliases(name_aliases_json)}
        if name_aliases_json is not None
        else {}
    )

    rows: list[PlayerPoolPlayer] = []
    game_options_by_key: dict[str, GameOption] = {}
    for player in players:
        key = game_key(player)
        game_id = "-".join(sorted(key))
        if game_id not in game_options_by_key:
            game_options_by_key[game_id] = GameOption(key=game_id, label=game_label(player))

        saved_entry = saved_entries.get(player.player)
        player_defaults = _resolve_player_defaults(player.player, defaults_by_player, name_aliases)
        player_defaults["game_matchup"] = _resolve_team_factor_default(
            player.opponent, player.position, team_factors_by_key
        )
        player_defaults["weather"] = _resolve_weather_default(game_id, weather_by_key)
        direct_scores = _resolve_direct_scores(player.position, saved_entry, player_defaults)
        effective_env, override_env, suggested_env = _resolve_game_environment(
            player, saved_entry, game_env_by_key.get(game_id)
        )
        default_standalone = _resolve_default_standalone(player.player, defaults_by_player, name_aliases)
        standalone = _resolve_standalone(player.position, saved_entry, default_standalone)
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
                standalone=standalone,
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
