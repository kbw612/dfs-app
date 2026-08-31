"""
Player Pool: a weekly, manually-scored replacement for the two Google
Sheets described in planning -- one listing every player in the contest
(grouped by position, sorted by salary, already covered by the DK/
ownership snapshot this reuses) and one scoring each player on a handful
of judgment calls (Game Environment, Game Matchup, Ownership, Volume/
Opportunities, Talent/Explosiveness -- Game Matchup and Salary Value for
DSTs) to decide who's actually worth rostering that week.

Every score field is optional and, when set, constrained to 1.0-3.0 with
decimals allowed (e.g. 1.5, 2.25) -- not tied to a fixed 0/.5/1 scale.
Total is just the sum of whichever fields are filled in for a given
player (see services/player_pool/engine.py's entry_total()), which is why
e.g. a QB scored on Ownership + Volume alone still gets a sensible total
without every position needing every field populated.

PlayerPoolEntry is the persisted, per-(season, week, player) record for
the fields Player Pool still owns directly -- Game Matchup, Ownership,
and Salary Value are expected to be re-entered fresh most weeks since the
underlying game/ownership context changes weekly (see
repositories/player_pool/entries_repo.py). PlayerPoolEntry.game_environment
is an *override* only -- leaving it unset doesn't mean "unscored", it
means "use whatever backend/services/game_environment/scoring.py's
formula suggests from that game's Vegas-line data" (see
services/player_pool/engine.py and PlayerPoolPlayer.game_environment_*
below for how the override and the suggestion combine).

Volume and Talent are *not* here -- see backend/schemas/player_attributes/
player_attributes.py for those two. They're facts about the player
themselves (carried forward from the most recent earlier week rather than
re-entered fresh), not about Player Pool specifically, so they live in
their own shared resource the same way GameEnvironmentEntry does (see
below).

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
    player: str

    # Override only -- None means "use the Game Environment formula's
    # suggestion," not "unscored." See this module's docstring.
    game_environment: _Score = _score_field()
    game_matchup: _Score = _score_field()
    ownership: _Score = _score_field()
    # DST-only -- there's no separate "ownership"/"talent" concept for a
    # defense, just how attractively priced it is this week.
    salary_value: _Score = _score_field()


class PlayerPoolPlayer(BaseModel):
    """One row in the Player Pool list -- base player info (from the
    DK/ownership snapshot) merged with this week's resolved scores (saved
    this week, carried forward for volume/talent, defaulted to a neutral
    2.0 for game_matchup/ownership/game_environment when a new week
    hasn't scored this player yet, or None if genuinely unscored -- see
    compute_player_pool()) and the computed total.

    game_environment is the *effective* value actually counted in `total`
    (the explicit override if one's been saved, otherwise the formula's
    suggestion -- which itself falls back to 2.0 when there's no Game
    Environment data for this game yet, so this is never None).
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
    # loaded (None before ownership projections exist for the week, same
    # as everywhere else in this app).
    ownership_pct: Optional[float] = None

    game_environment: _Score = None
    game_environment_override: _Score = None
    game_environment_suggested: _Score = None
    game_matchup: _Score = None
    ownership: _Score = None
    volume: _Score = None
    talent: _Score = None
    salary_value: _Score = None

    total: float


class GameOption(BaseModel):
    key: str
    label: str


class PlayerPoolResult(BaseModel):
    players: list[PlayerPoolPlayer]
    games: list[GameOption]
    game_environment: list[GameEnvironmentEntry]
