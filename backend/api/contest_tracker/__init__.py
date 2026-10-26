"""
Results Tracker endpoints (mounted at /api/contest-tracker); see
backend/schemas/contest_tracker/contest_tracker.py for the data model.

- GET    ""                          the season's grid data with ROI/totals
- POST   "/contests"                 add a contest {name}
- PATCH  "/contests/{id}"            rename {name}
- DELETE "/contests/{id}"            remove a contest and all its entries
- PUT    "/entries"                  add or replace one contest/week entry
- DELETE "/entries"                  mark a contest/week not played
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.repositories.contest_tracker.contest_tracker_repo import load_tracker, save_tracker
from backend.schemas.contest_tracker.contest_tracker import ContestTrackerResult, TrackerContest, TrackerEntry
from backend.services.contest_tracker.summary import summarize

router = APIRouter(prefix="/contest-tracker")


class ContestName(BaseModel):
    name: str = Field(min_length=1, max_length=60)


def _check_name_free(data, name: str, except_id: str | None = None) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Contest name can't be empty.")
    if any(c.name.lower() == name.lower() and c.id != except_id for c in data.contests):
        raise HTTPException(status_code=400, detail=f"A contest named '{name}' already exists.")
    return name


@router.get("", response_model=ContestTrackerResult)
def get_tracker(season: int) -> ContestTrackerResult:
    return summarize(load_tracker(settings.nfl_data_dir, season))


@router.post("/contests", response_model=ContestTrackerResult)
def add_contest(season: int, body: ContestName) -> ContestTrackerResult:
    data = load_tracker(settings.nfl_data_dir, season)
    data.contests.append(TrackerContest(id=uuid.uuid4().hex[:8], name=_check_name_free(data, body.name)))
    save_tracker(settings.nfl_data_dir, data)
    return summarize(data)


@router.patch("/contests/{contest_id}", response_model=ContestTrackerResult)
def rename_contest(season: int, contest_id: str, body: ContestName) -> ContestTrackerResult:
    data = load_tracker(settings.nfl_data_dir, season)
    contest = next((c for c in data.contests if c.id == contest_id), None)
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found.")
    contest.name = _check_name_free(data, body.name, except_id=contest_id)
    save_tracker(settings.nfl_data_dir, data)
    return summarize(data)


@router.delete("/contests/{contest_id}", response_model=ContestTrackerResult)
def delete_contest(season: int, contest_id: str) -> ContestTrackerResult:
    data = load_tracker(settings.nfl_data_dir, season)
    if not any(c.id == contest_id for c in data.contests):
        raise HTTPException(status_code=404, detail="Contest not found.")
    data.contests = [c for c in data.contests if c.id != contest_id]
    data.entries = [e for e in data.entries if e.contest_id != contest_id]
    save_tracker(settings.nfl_data_dir, data)
    return summarize(data)


@router.put("/entries", response_model=ContestTrackerResult)
def put_entry(season: int, entry: TrackerEntry) -> ContestTrackerResult:
    data = load_tracker(settings.nfl_data_dir, season)
    if not any(c.id == entry.contest_id for c in data.contests):
        raise HTTPException(status_code=404, detail="Contest not found.")
    data.entries = [e for e in data.entries if not (e.contest_id == entry.contest_id and e.week == entry.week)]
    data.entries.append(entry)
    save_tracker(settings.nfl_data_dir, data)
    return summarize(data)


@router.delete("/entries", response_model=ContestTrackerResult)
def delete_entry(season: int, contest_id: str, week: int) -> ContestTrackerResult:
    data = load_tracker(settings.nfl_data_dir, season)
    data.entries = [e for e in data.entries if not (e.contest_id == contest_id and e.week == week)]
    save_tracker(settings.nfl_data_dir, data)
    return summarize(data)
