"""
This week's DK salary export, parsed in-memory by
backend/services/dk_salary/dk_salary_loader.py's parse_dk_salary_csv() --
not persisted as JSON itself (see backend/repositories/dk_salary/
salary_snapshot_repo.py, which stores the raw uploaded CSV text instead
and re-parses it into one of these on every read). Shared by every tab
that needs salary/team/opponent for the full player universe -- Salary
Blocks and Player Pool both read this rather than each having their own
separate upload (see backend/api/ownership/position_blocks.py and
backend/api/player_pool/latest.py). ownership_pct is always None here --
DK's own export never includes ownership -- and gets opportunistically
filled in from the Ownership tab's snapshot when one exists for the same
week (see ownership_enrich.enrich_with_ownership_pct). The Ownership tab
keeps using its own file's salary for its own display; this snapshot is
what everything else uses.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.schemas.ownership.ownership import OwnershipPlayer


class DkSalarySnapshot(BaseModel):
    scraped_at: str
    source_url: str
    season: int
    week: int
    players: list[OwnershipPlayer]
