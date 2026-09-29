"""
Injury Report -- every player from the latest Depth Charts snapshot
(backend/schemas/depth_charts/snapshot.py) who currently carries a non-null
status, grouped by this week's game matchup (mirrors footballguys.com's own
"Weekly Injury Report By Team" page, which despite its name groups by game --
"Atlanta Falcons v CAR" sections listing both teams' injured players
together -- not by team alone). See backend/services/injury_report/
injury_report_engine.py for how this is built.

Reuses GameOption's own key/label/teams shape (backend/schemas/game_logs/
game_logs.py) for the grouping -- same "AWAY @ HOME" labeling, same
contest-scoping, same bye-week exclusion (a team with no game this week
just never appears in any group) as the Game Logs tab's own Game filter --
rather than inventing a second, slightly-different game-grouping concept.

No injury body-part/description field (footballguys' own table has one,
e.g. "Knee", "Hamstring") -- the depth-chart scrape this is built from only
ever carries the short status code (Q/D/O/IR/etc., see StatusCode in
frontend/src/statusCodes.ts), never a body part, so there's nothing to
surface here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InjuryPlayerEntry(BaseModel):
    team: str
    player: str
    position: str
    status: str
    # True if this (team, player) pair is currently flagged in Star Players
    # (backend/schemas/star_players/star_players.py) -- joined in once here
    # rather than requiring the frontend to fetch and join Star Players
    # itself, since this report is read-only display (no star-toggle
    # control of its own, unlike the Depth Charts tab).
    starred: bool
    # 1-based index of this player within their own position's depth-chart
    # array (see Snapshot's own "no stored rank" docstring in
    # backend/schemas/depth_charts/snapshot.py) -- computed fresh here off
    # that array order rather than stored anywhere, same reasoning as that
    # file gives for not storing rank on Player itself. Powers the frontend's
    # Position Depth chip filter (fixed 1-4 chips, same model as Usage Bump
    # Players' own "Position Depth" filter).
    depth: int


class InjuryGameGroup(BaseModel):
    key: str
    label: str
    teams: list[str]
    players: list[InjuryPlayerEntry] = Field(default_factory=list)


class InjuryReportResult(BaseModel):
    # Passed through from the depth-chart snapshot's own scraped_at, so the
    # frontend can show "as of" the same way the Depth Charts tab does --
    # this report is only ever as fresh as the last depth-chart scrape.
    scraped_at: str
    week: int
    # Games with zero injured players are left out entirely (nothing to
    # show), not included with an empty players list -- same "don't render
    # an empty section" convention as Depth Charts' own position rows.
    games: list[InjuryGameGroup] = Field(default_factory=list)
