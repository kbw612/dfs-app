"""
Change record schema for the diff engine (Section 2 of the design doc:
generate_diff()). One Change = one line in a changes_{timestamp}.jsonl file.
A player who changed appears exactly once, even if multiple things about
them changed -- `change_types` lists every dimension that differed for
that one record, in a fixed order: "status", "rank", then "other".

Player-level changes set team_abbrev/position/player and leave `field`
null. Team-level changes (currently just defensive_formation) set
team_abbrev/field instead and leave position/player null, and always use
change_types=["other"] (a team-level field can't also have a status/rank,
so there's nothing to combine it with).

No severity field -- the endpoint returning these just reports what
changed; ranking/prioritizing is a downstream concern, not this schema's
job.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel


class Change(BaseModel):
    team_abbrev: Optional[str] = None
    position: Optional[str] = None
    player: Optional[str] = None
    field: Optional[str] = None
    change_types: list[Literal["status", "rank", "other"]]
    previous: Any = None
    current: Any = None
