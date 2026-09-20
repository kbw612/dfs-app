"""
Team Default Factors: a per-(season, team, position) baseline "how tough
is this team's defense against this offensive position" judgment, set
once in Settings' Team Default Factors grid -- not tied to any specific
week, contest, or platform, same "set-once-per-season" convention as
Player Default Factors (see backend/schemas/player_defaults/
player_defaults.py).

Unlike Player Default Factors (keyed by player name, feeding Volume/
Talent), this is keyed by (team, position) and feeds Player Pool's
existing Matchup field (`game_matchup` in backend/schemas/player_pool/
player_pool.py): for a given week, a player's Matchup starts from
*their opponent's* Team Default Factor at the player's own position --
e.g. a WR playing a team whose WR factor is set to 3.0 starts that week
at 3.0 instead of a flat neutral 2.0 -- unless that exact week already
has an explicit Matchup save, which always wins (see
backend/services/player_pool/engine.py's compute_player_pool). Editing
the resolved Matchup value directly in Player Rankings only ever affects
that one week's PlayerPoolEntry, never this Team Default Factor itself,
same relationship Volume/Talent already have with their own per-player
Default.

`position` is one of QB/RB/WR/TE/DST -- DST's own Team Default Factor
represents the flip side of the same field (how tough a matchup that
team's OWN offense is for an opposing DST to score against), reusing the
exact same (team, position) shape rather than a separate concept, since
Player Pool's own game_matchup field already treats DST this way (see
_DST_FIELDS in engine.py).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TeamFactorEntry(BaseModel):
    season: int
    team: str
    position: str

    # None means "never explicitly set" -- Player Pool's own fallback
    # chain (per-week override, then this, then a flat 2.0) treats a
    # missing entry the same as an explicitly-None one, so there's no
    # need to pre-populate all 32 teams x 5 positions on disk just to
    # represent "still at the neutral default." The Settings grid itself
    # displays 2.0 in an unset cell rather than leaving it blank (unlike
    # Player Default Factors' Volume/Talent inputs), but that's a display
    # choice, not a stored value -- see SettingsView.tsx's own comment.
    factor: Optional[float] = Field(default=None, ge=1.0, le=3.0)
