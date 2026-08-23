"""
Pydantic models for the depth-chart snapshot -- this is the schema
documented in Section 2 of the design doc. Key decisions baked in here,
carried over from that doc:

- No stored `rank` or `depth` field on Player. Rank is just the player's
  index in its position's array; storing it would be a second source of
  truth that could drift from the actual array order.
- `defensive_formation` IS stored (unlike rank/depth) because it encodes a
  business rule (MLB-vs-NT presence), not mechanical array-index math.
- `messages` lives at the top level of the snapshot, not in a separate file,
  since it explains that snapshot's own data (e.g. why a team_abbrev is
  null).
- No `player_id` -- deferred per the design doc; matching is by name only
  for now.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Player(BaseModel):
    player: str
    status: Optional[str] = None


class Team(BaseModel):
    team_abbrev: Optional[str] = None
    team_name: str
    defensive_formation: Optional[str] = None
    positions: dict[str, list[Player]] = Field(default_factory=dict)


class Message(BaseModel):
    level: Literal["error", "warning", "info"]
    step: str
    message: str


class Snapshot(BaseModel):
    scraped_at: str
    source_url: str
    messages: list[Message] = Field(default_factory=list)
    teams: list[Team] = Field(default_factory=list)
