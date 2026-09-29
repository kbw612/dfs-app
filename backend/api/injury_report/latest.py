"""
GET /latest?season=&week=&platform=&contest= (mounted at
/api/injury-report/latest -- see backend/api/injury_report/__init__.py).
Backs the Injury Report tab -- every player from the latest Depth Charts
snapshot who currently carries a non-null status, grouped by this week's
game matchup, with each entry's gold-star flag joined in from Star Players.
See backend/services/injury_report/injury_report_engine.py for the full
computation.

404s if no depth chart has been scraped yet -- same "retrieve it first"
convention as Depth Charts' own /latest endpoint (backend/api/depth_charts/
latest.py); there's nothing to build a report from otherwise. A missing
Schedule file degrades gracefully instead -- every team just has no game to
group under, so the whole report comes back with an empty `games` list
rather than erroring, same "nothing to narrow by yet" convention as Game
Logs' own missing-Schedule handling.

`season`/`week`/`platform`/`contest` (contest defaults to "Classic Main",
same default every other contest-scoped endpoint in this app uses) are used
only to resolve this week's Schedule row per team and, via `contest`, to
narrow the report down to that contest's own DK salary slate -- same
derivation as Game Logs' own `contest_teams` (backend/api/game_logs/
game_logs.py). None of season/week/platform/contest affect which depth-chart
snapshot is read -- that's always just "whatever the latest scrape says
right now," same as the Depth Charts tab itself.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.repositories.star_players.star_players_repo import load_star_players
from backend.schemas.injury_report.injury_report import InjuryReportResult
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.injury_report.injury_report_engine import build_injury_report
from backend.services.schedule.schedule_loader import parse_schedule_csv

router = APIRouter()


@router.get("/latest", response_model=InjuryReportResult)
def injury_report_latest_endpoint(
    season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"
) -> InjuryReportResult:
    snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    if snapshot_path is None:
        raise HTTPException(status_code=404, detail="No depth chart scraped yet -- retrieve one first.")
    snapshot = load_snapshot(snapshot_path)

    schedule_csv = load_schedule_csv(settings.nfl_data_dir, season)
    schedule_rows = parse_schedule_csv(schedule_csv) if schedule_csv is not None else []

    star_players = load_star_players(settings.star_players_json)

    contest_teams: set[str] | None = None
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is not None:
        salary_snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
        contest_teams = {p.team for p in salary_snapshot.players}

    return build_injury_report(snapshot, schedule_rows, week, star_players, contest_teams)
