"""
Player Groups endpoints (mounted at /api/player-groups):

- GET    ""          the week's saved groups with preview figures
- PUT    ""          save the groups (validated); returns them with figures
- GET    "/pool"     the contest's players, filtered by game/position/team/name/My Player Pool
                     and sorted salary high to low, plus the game chips
- POST   "/import"   merge (or replace with) a Blink groups file
- POST   "/export"   the groups as Blink's CSV text
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.my_player_pool.my_player_pool_repo import load_membership
from backend.repositories.player_groups.player_groups_repo import load_groups, save_groups
from backend.schemas.player_groups.player_groups import GroupsState, PlayerGroup, PoolResult
from backend.services.player_groups.groups_file import merge_groups, parse_groups_csv, write_groups_csv
from backend.services.player_groups.pool import filter_pool, min_salaries, parse_pool, summarize, validate_groups

router = APIRouter(prefix="/player-groups")


def _pool(season: int, week: int, platform: str, contest: str):
    csv_text = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if csv_text is None:
        raise HTTPException(status_code=404, detail=f"No DK salary file uploaded for season {season} week {week} -- upload it in the Settings tab.")
    return parse_pool(csv_text)


def _state(groups: list[PlayerGroup], players) -> GroupsState:
    warnings = []
    summaries = summarize(groups, players)
    for g in summaries:
        if g.missing_ids:
            warnings.append(f"'{g.name}' has {len(g.missing_ids)} player(s) not in this week's salary file.")
    return GroupsState(groups=summaries, warnings=warnings)


@router.get("", response_model=GroupsState)
def get_groups(season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main") -> GroupsState:
    players, _games = _pool(season, week, platform, contest)
    return _state(load_groups(settings.nfl_data_dir, season, week, platform, contest), players)


class GroupsBody(BaseModel):
    groups: list[PlayerGroup]


@router.put("", response_model=GroupsState)
def put_groups(season: int, week: int, body: GroupsBody, platform: str = "DraftKings", contest: str = "Classic Main") -> GroupsState:
    problems = validate_groups(body.groups)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))
    players, _games = _pool(season, week, platform, contest)
    save_groups(settings.nfl_data_dir, season, week, platform, contest, body.groups)
    return _state(body.groups, players)


@router.get("/pool", response_model=PoolResult)
def get_pool(
    season: int,
    week: int,
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    game: list[str] = Query(default=[]),
    position: str = "ALL",
    team: str = "",
    q: str = "",
    my_pool: bool = False,
    hide_min: bool = False,
) -> PoolResult:
    players, games = _pool(season, week, platform, contest)
    membership = load_membership(settings.nfl_data_dir, season, week, platform, contest)
    names = {name for name, in_pool in membership.items() if in_pool}
    return PoolResult(
        games=games,
        players=filter_pool(players, game, position, team, q, names if my_pool else None, hide_min),
        min_salaries=min_salaries(players),
        my_pool_count=sum(1 for p in players if p.name in names),
    )


@router.post("/import", response_model=GroupsState)
async def import_groups(
    season: int,
    week: int,
    file: UploadFile = File(...),
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    replace_all: bool = False,
) -> GroupsState:
    try:
        imported = parse_groups_csv((await file.read()).decode("utf-8-sig"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    players, _games = _pool(season, week, platform, contest)
    merged = merge_groups(load_groups(settings.nfl_data_dir, season, week, platform, contest), imported, replace_all)
    save_groups(settings.nfl_data_dir, season, week, platform, contest, merged)
    return _state(merged, players)


class ExportResult(BaseModel):
    filename: str
    csv: str


@router.post("/export", response_model=ExportResult)
def export_groups(week: int, body: GroupsBody, contest: str = "Classic Main") -> ExportResult:
    problems = validate_groups(body.groups)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))
    slug = contest.lower().replace(" ", "-")
    return ExportResult(filename=f"nfl-dk-{slug}-groups-week{week}.csv", csv=write_groups_csv(body.groups))
