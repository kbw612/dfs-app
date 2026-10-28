"""
GET /exposure (mounted at /api/contest-results/exposure) --
season=&week=&platform=&contest=&scope=&position=&sort=&compare=. FLEX counts
and player exposure among the contest's top lineups, finished (the frontend
only displays it). Scopes: top10 / top50 / top100 / all (every entry in the
uploaded standings file) / optimal (the cached top-10 optimal lineups).

Field % is each player's total %Drafted in the contest (summed over slots, same
number the Contest results table shows); Pts is his actual FPTS. `compare=true`
adds the exposure of the user's saved Lineup Analyzer pool for the same week
(null/unavailable when no pool was uploaded).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.repositories.contest_results.contest_standings_repo import load_contest_standings_csv
from backend.repositories.contest_results.optimal_lineups_cache_repo import load_top10_by_points
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from backend.repositories.lineup_analyzer.pool_repo import load_pool
from backend.schemas.exposure.exposure import ExposureResult, ExposureView
from backend.services.contest_results.contest_results_engine import _total_pct_drafted_by_player
from backend.services.contest_results.contest_standings_parser import parse_contest_standings_csv, parse_lineup_text
from backend.services.dk_salary.dk_salary_loader import parse_dk_salary_csv
from backend.services.exposure.exposure import LineupPlayer, build_exposure, make_view

router = APIRouter()

TOP_SCOPES = {"top10": 10, "top50": 50, "top100": 100}


def _entry_lineup(lineup_text: str, salary_lookup: dict) -> list[LineupPlayer] | None:
    """One contest entry -> LineupPlayers, or None if any player isn't in the
    salary file (true position/team/salary come from it)."""
    out = []
    for slot, name in parse_lineup_text(lineup_text):
        p = salary_lookup.get(name)
        if p is None:
            return None
        out.append(LineupPlayer(slot, name, p.position, p.team, p.salary))
    return out if len(out) == 9 else None


@router.get("/exposure", response_model=ExposureView)
def exposure_endpoint(
    season: int,
    week: int,
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    scope: str = "top10",
    position: str = "ALL",
    sort: str = "exposure",
    compare: bool = False,
) -> ExposureView:
    standings_csv = load_contest_standings_csv(settings.nfl_data_dir, season, week, platform, contest)
    if standings_csv is None:
        raise HTTPException(status_code=404, detail=f"No contest standings uploaded yet for season {season} week {week} -- upload it in the Settings tab.")
    salary_csv = load_salary_csv(settings.nfl_data_dir, season, week, platform, contest)
    if salary_csv is None:
        raise HTTPException(status_code=404, detail=f"No DK salary file uploaded yet for season {season} week {week} -- upload it in the Settings tab.")

    standings = parse_contest_standings_csv(standings_csv)
    snapshot, _messages = parse_dk_salary_csv(salary_csv, season, week)
    lookup = {p.player.strip(): p for p in snapshot.players}
    field = _total_pct_drafted_by_player(standings.reference_rows)
    pts = {r.player: r.fpts for r in standings.reference_rows}

    entry_lineups = [lu for lu in (_entry_lineup(e.lineup_text, lookup) for e in standings.entries) if lu is not None]

    # The user's saved analyzer pool for this week, as exposure per player.
    pool = load_pool(settings.nfl_data_dir, season, week, platform, contest)
    compare_available = bool(pool and pool["lineups"])
    compare_pct: dict[str, float] | None = None
    if compare and compare_available:
        import csv
        import io

        id_to_name = {(r.get("ID") or "").strip(): (r.get("Name") or "").strip() for r in csv.DictReader(io.StringIO(salary_csv))}
        pool_lineups = []
        for lineup in pool["lineups"]:
            names = [id_to_name.get(pid) or name.strip() for name, pid in lineup]
            if all(n in lookup for n in names):
                pool_lineups.append([LineupPlayer("", n, lookup[n].position, lookup[n].team, lookup[n].salary) for n in names])
        compare_pct = {p.name: p.exposure_pct for p in build_exposure("pool", "pool", pool_lineups).players} if pool_lineups else {}

    results: list[ExposureResult] = []
    for key, n in TOP_SCOPES.items():
        subset = entry_lineups[:n]
        if subset:
            results.append(build_exposure(key, f"Top {n}", subset, field, pts, compare_pct))
    if entry_lineups:
        results.append(build_exposure("all", f"All {len(entry_lineups)} in file", entry_lineups, field, pts, compare_pct))

    optimal = load_top10_by_points(settings.nfl_data_dir, season, week, platform, contest)
    if optimal:
        optimal_lineups = []
        for lineup in optimal:
            cells = []
            for pl in lineup.players:
                p = lookup.get(pl.player.strip())
                cells.append(LineupPlayer(pl.roster_position, pl.player, pl.position, p.team if p else "", pl.salary))
            optimal_lineups.append(cells)
        results.append(build_exposure("optimal", "Optimal top 10", optimal_lineups, field, pts, compare_pct))

    if not results:
        raise HTTPException(status_code=404, detail="No lineups found in the uploaded contest standings.")
    return make_view(results, scope, position, sort, "Field %", compare_available)
