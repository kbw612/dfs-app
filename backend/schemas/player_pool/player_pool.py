"""
Player Pool: a weekly, manually-scored replacement for the two Google
Sheets described in planning -- one listing every player in the contest
(grouped by position, sorted by salary, already covered by the DK/
ownership snapshot this reuses) and one scoring each player on a handful
of judgment calls (Game Environment, Game Matchup, Ownership, Volume/
Opportunities, Talent/Explosiveness -- Game Matchup and Salary Value for
DSTs) to decide who's actually worth rostering that week.

Every score field is optional and, when set, constrained to 1.0-3.0 with
decimals allowed (e.g. 1.5, 2.25) -- not tied to a fixed 1/2/3 scale.
Total is just the sum of whichever fields are filled in for a given
player (see services/player_pool/engine.py's entry_total()), which is why
e.g. a QB scored on Ownership + Volume alone still gets a sensible total
without every position needing every field populated.

Game Environment shares this same 1.0-3.0 range -- it used to be
constrained to its own 0.0-1.0 scale (0/0.5/1, matching backend/services/
game_environment/scoring.py's rule as originally described), which gave
it half the maximum weight of the other fields in Total. That asymmetry
was intentional at the time but was later reversed so every field weighs
the same (see that module's docstring and engine.py's
_DEFAULT_GAME_ENVIRONMENT); a previously-saved override on the old scale
needs remapping (old * 2 + 1) rather than being read as-is.

PlayerPoolEntry is the persisted, per-(season, week, platform, player)
record for every field Player Pool saves directly -- Game Matchup, Ownership, and
Salary Value are expected to be re-entered fresh most weeks since the
underlying game/ownership context changes weekly; Volume and Talent are
saved the same way, one explicit value per week, no carry-forward from an
earlier week (see repositories/player_pool/entries_repo.py).
PlayerPoolEntry.game_environment is an *override* only -- leaving it
unset doesn't mean "unscored", it means "use whatever
backend/services/game_environment/scoring.py's formula suggests from that
game's Vegas-line data" (see services/player_pool/engine.py and
PlayerPoolPlayer.game_environment_* below for how the override and the
suggestion combine).

When a week has no explicit Volume/Talent save, Player Pool falls back to
that player's Player Default instead of leaving the cell blank -- see
backend/schemas/player_defaults/player_defaults.py. A Default is set once
per player per season (Settings' Player Default Settings grid), not tied
to a specific week; it's what "initially populates" Player Pool for a
player before anyone has explicitly scored them that week. Setting a
Default never touches an already-saved PlayerPoolEntry for any week --
the two are separate resources, resolved together only at read time (see
services/player_pool/engine.py's compute_player_pool).

GameEnvironmentEntry -- the shared, per-(season, week, game) Vegas-line
input (spread, over/under, each team's implied total) multiple tabs can
draw on -- now lives in backend/schemas/game_environment/
game_environment.py instead of here, since it's not Player-Pool-specific.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from backend.schemas.game_environment.game_environment import GameEnvironmentEntry

_Score = Optional[float]


def _score_field() -> _Score:
    return Field(default=None, ge=1.0, le=3.0)


class PlayerPoolEntry(BaseModel):
    season: int
    week: int
    # Determines the saved file's name (see repositories/player_pool/
    # entries_repo.py's platform_file_prefix usage) -- same reasoning as
    # Player Selection's PlayerSelectionOverride.platform. Defaults to
    # "DraftKings", the only platform with a real file format today.
    platform: str = "DraftKings"
    player: str

    # Override only -- None means "use the Game Environment formula's
    # suggestion," not "unscored." See this module's docstring. Same
    # 1.0-3.0 range as every other field below.
    game_environment: _Score = _score_field()
    game_matchup: _Score = _score_field()
    ownership: _Score = _score_field()
    # DST-only -- there's no separate "ownership"/"talent" concept for a
    # defense, just how attractively priced it is this week.
    salary_value: _Score = _score_field()
    # None here means "no explicit save for this exact week" -- falls back
    # to the player's Player Default, then to a neutral 2.0, purely at read
    # time (see this module's docstring and services/player_pool/
    # engine.py's _resolve_direct_scores). No carry-forward from an
    # earlier week's save.
    volume: _Score = _score_field()
    talent: _Score = _score_field()


class PlayerPoolPlayer(BaseModel):
    """One row in the Player Pool list -- base player info (from the
    DK/ownership snapshot) merged with this week's resolved scores (saved
    this week, carried forward for volume/talent, defaulted to a neutral
    2.0 for game_matchup/ownership/game_environment when a new week hasn't
    scored this player yet, or None if genuinely unscored -- see
    compute_player_pool()) and the computed total.

    game_environment is the *effective* value actually counted in `total`
    (the explicit override if one's been saved, otherwise the formula's
    suggestion -- which itself falls back to a neutral 2.0 when there's no
    Game Environment data for this game yet, so this is never None).
    game_environment_override is the raw saved override only (None if
    this player hasn't been explicitly overridden this week) -- the edit
    form seeds its input from this, not from the blended
    `game_environment`, so leaving the input blank and saving doesn't
    accidentally freeze in whatever the suggestion happened to be at that
    moment. game_environment_suggested is the formula's own output (or
    its 2.0 fallback), shown as a hint next to that input."""

    player: str
    position: str
    team: str
    opponent: str
    is_home: Optional[bool] = None
    salary: int
    # Reference only -- from the Ownership tab's snapshot when it's
    # loaded. None only means "the Ownership tab has no snapshot at all
    # for this (season, week) yet" -- once one exists, a player who's
    # simply absent from it is 0.0 (0% owned), not None, so the Player
    # Rankings grid can tell "not retrieved" (show nothing) apart from
    # "retrieved, this player just isn't projected to be owned" (show
    # 0%). See services/player_pool/engine.py's ownership_retrieved
    # param, set by api/player_pool/latest.py.
    ownership_pct: Optional[float] = None
    # 1-indexed depth-chart rank (e.g. RB1, RB2) -- same cross-referenced
    # value as OwnershipPlayer.depth_rank (see backend/services/ownership/
    # depth_rank.py), filled in here purely so Settings' Player Default
    # Settings grid can narrow to each position's top depth-chart slots
    # (backend/api/player_pool/latest.py). None if there's no depth-chart
    # snapshot yet or this name doesn't match one -- callers treat that as
    # "rank unknown," not "buried on the depth chart." Named depth_rank
    # (not rank) to avoid colliding with the Player Rankings tab's
    # Total-based score, a wholly different concept.
    depth_rank: Optional[int] = None

    game_environment: _Score = None
    game_environment_override: _Score = None
    game_environment_suggested: _Score = None
    game_matchup: _Score = None
    ownership: _Score = None
    volume: _Score = None
    talent: _Score = None
    salary_value: _Score = None

    # Player Rankings' "Expected FPTS" column -- multiplier * salary / 1000
    # (see backend/services/salary_multiplier/engine.py), using whichever
    # multiplier resolved for this computation's platform (Settings'
    # Salary Multiplier field, or its computed default). Purely
    # informational -- unlike every field above, it's never summed into
    # `total`, since it isn't a judgment-call score, just a salary-derived
    # reference figure. Always a real number (there's no "no multiplier"
    # state, see resolve_multiplier), independent of position -- DSTs get
    # one too, unlike Game Environment/Ownership/Volume/Talent.
    expected_fpts: float = 0.0

    total: float


class GameOption(BaseModel):
    key: str
    label: str


class PlayerPoolResult(BaseModel):
    players: list[PlayerPoolPlayer]
    games: list[GameOption]
    game_environment: list[GameEnvironmentEntry]
