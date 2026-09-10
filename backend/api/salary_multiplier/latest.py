"""
GET /latest?platform= (mounted at /api/salary-multiplier/latest -- see
backend/api/salary_multiplier/__init__.py). No season/week param -- the
multiplier is scoped to platform alone (see backend/schemas/
salary_multiplier/salary_multiplier.py). `multiplier` is always the
resolved value (an explicit override if one's been saved, otherwise the
computed default -- see backend/services/salary_multiplier/engine.py);
`override` is the raw saved value only, None if this platform has never
been explicitly set, so Settings' input can seed itself from the truth
of what's actually been saved rather than the blended value.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.salary_multiplier.salary_multiplier_repo import load_multipliers
from backend.schemas.salary_multiplier.salary_multiplier import SalaryMultiplierResult
from backend.services.salary_multiplier.engine import resolve_multiplier

router = APIRouter()


@router.get("/latest", response_model=SalaryMultiplierResult)
def salary_multiplier_latest_endpoint(platform: str = "DraftKings") -> SalaryMultiplierResult:
    override = load_multipliers(settings.salary_multiplier_dir).get(platform)
    return SalaryMultiplierResult(platform=platform, multiplier=resolve_multiplier(platform, override), override=override)
