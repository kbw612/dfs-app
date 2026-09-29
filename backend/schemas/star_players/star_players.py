"""
Star Players: a hand-curated, season-wide flag for "this player is a
difference-maker" -- set from the Depth Charts tab's star icon (see
frontend/src/components/DepthChartsView.tsx), at any position, not just
skill positions that already carry their own fantasy-relevant scoring
elsewhere in the app (Player Pool's Volume/Talent/Ownership). The
motivating case: flagging a team's star offensive linemen, defensive
linemen, linebackers, or defensive backs, so a glance at that team's
depth chart shows whether a difference-maker is currently hurt/out even
though the app has no other scoring signal for that position.

Keyed by (team, player) rather than player name alone -- same rationale
as Usage Bump Players' own (team, player) keying (see
backend/schemas/usage_bump/usage_bump_players.py): the depth-chart
snapshot itself matches players by name only (no player_id -- see
backend/schemas/depth_charts/snapshot.py's docstring), so two same-named
players on different teams would otherwise collide.

No season/week/platform/contest scoping -- same "set once, persists"
convention as Usage Bump Players (backend/config.py's
usage_bump_players_json), since the Depth Charts tab this feeds has no
season selector of its own either.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StarPlayerEntry(BaseModel):
    team: str
    player: str


class StarPlayersResult(BaseModel):
    players: list[StarPlayerEntry] = Field(default_factory=list)
