"""
PUT /entry (mounted at /api/salary-multiplier/entry -- see
backend/api/salary_multiplier/__init__.py). Body is a full
SalaryMultiplierEntry -- saves (or, if multiplier is null, clears) that
platform's explicit override. Returns the same resolved shape GET
/latest does (not just an echo of the input) so Settings' input can
immediately show the right value even when the save cleared the override
back to the computed default.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.salary_multiplier.salary_multiplier_repo import save_multiplier
from backend.schemas.salary_multiplier.salary_multiplier import SalaryMultiplierEntry, SalaryMultiplierResult
from backend.services.salary_multiplier.engine import resolve_multiplier

router = APIRouter()


@router.put("/entry", response_model=SalaryMultiplierResult)
def salary_multiplier_entry_endpoint(entry: SalaryMultiplierEntry) -> SalaryMultiplierResult:
    save_multiplier(settings.salary_multiplier_dir, entry.platform, entry.multiplier)
    return SalaryMultiplierResult(
        platform=entry.platform,
        multiplier=resolve_multiplier(entry.platform, entry.multiplier),
        override=entry.multiplier,
    )
