"""
Lineup Analyzer endpoints (mounted at /api/lineup-analyzer):

- POST /upload: one or more optimizer CSVs (~1,000 lineups each, "Name (id)"
  cells). Merged with / replaces the stored pool and de-duplicated across files.
- GET /info: stored pool summary + default weights + feature names.
- POST /analyze: scores the stored pool against the slate's synthetic field
  (see backend/services/lineup_analyzer/scorer.py), returns the top rows with
  per-factor contributions, plus an optional exposure/overlap-limited portfolio.
"""

from __future__ import annotations

import hashlib

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.config import settings
from backend.repositories.dk_salary.salary_snapshot_repo import load_salary_csv
from datetime import datetime, timezone

from backend.repositories.lineup_analyzer.pool_repo import delete_result, load_pool, load_result, save_pool, save_result
from backend.services.dk_salary.ownership_enrich import load_projected_ownership_players
from backend.repositories.ownership.projections_repo import load_projections_csv
from backend.repositories.vegas_lines.vegas_lines_repo import load_vegas_lines
from backend.services.lineup_analyzer.upside_env import team_lines
from backend.services.lineup_analyzer.live_slate import SlateError, build_live_week
from backend.services.lineup_analyzer.pool_parser import lineup_key, parse_pool_csv
from backend.schemas.exposure.exposure import ExposureResult, ExposureView
from backend.services.exposure.exposure import LineupPlayer, build_exposure, make_view
from backend.services.lineup_analyzer import flags as flag_service
from backend.services.lineup_analyzer import scorer
from backend.schemas.lineup_analyzer.flags import FlagSettings, FlagSummary, LineupFlag
from backend.repositories.depth_charts.snapshot_repo import find_latest_snapshot, load_snapshot
from backend.repositories.weather.weather_repo import load_weather
from backend.services.ownership.depth_rank import build_depth_rank_lookup

router = APIRouter(prefix="/lineup-analyzer")


class FileSummary(BaseModel):
    name: str
    rows: int
    new_unique: int


class PoolInfo(BaseModel):
    # Hash of the slate inputs (salary file, ownership projections, Vegas
    # lines); the tab compares it with the one from the last analysis to offer
    # a re-analyze when ownership (or lines/salaries) changed.
    slate_signature: str = ""
    lineup_count: int
    files: list[FileSummary]
    feature_names: list[str]
    default_weights: dict[str, float]


def slate_signature(season: int, week: int, platform: str, contest: str) -> str:
    h = hashlib.sha1()
    h.update((load_salary_csv(settings.nfl_data_dir, season, week, platform, contest) or "").encode())
    h.update((load_projections_csv(settings.nfl_data_dir, season, week, platform) or "").encode())
    lines = load_vegas_lines(settings.nfl_data_dir, season, week)
    h.update((lines.model_dump_json() if lines else "").encode())
    return h.hexdigest()[:16]


def _info(pool: dict | None, signature: str = "") -> PoolInfo:
    return PoolInfo(
        slate_signature=signature,
        lineup_count=len(pool["lineups"]) if pool else 0,
        files=[FileSummary(**f) for f in (pool["files"] if pool else [])],
        feature_names=scorer.ALL_FEATURE_NAMES,
        default_weights=scorer.default_weights(),
    )


@router.get("/info", response_model=PoolInfo)
def pool_info(season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main") -> PoolInfo:
    return _info(load_pool(settings.nfl_data_dir, season, week, platform, contest), slate_signature(season, week, platform, contest))


@router.post("/upload", response_model=PoolInfo)
async def upload_pool(
    season: int,
    week: int,
    files: list[UploadFile] = File(...),
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    replace: bool = True,
) -> PoolInfo:
    existing = None if replace else load_pool(settings.nfl_data_dir, season, week, platform, contest)
    lineups: list = list(existing["lineups"]) if existing else []
    summaries: list = list(existing["files"]) if existing else []
    copies: list = list(existing.get("copies", [1] * len(lineups))) if existing else []
    seen = {lineup_key([tuple(c) for c in l]): i for i, l in enumerate(lineups)}
    for f in files:
        try:
            parsed = parse_pool_csv((await f.read()).decode("utf-8-sig"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{f.filename}: {exc}")
        new = 0
        for lineup in parsed:
            key = lineup_key(lineup)
            if key in seen:
                copies[seen[key]] += 1  # an extra copy: dropped, but remembered so it can be flagged
                continue
            seen[key] = len(lineups)
            lineups.append([list(c) for c in lineup])
            copies.append(1)
            new += 1
        summaries.append({"name": f.filename or "file", "rows": len(parsed), "new_unique": new})
    data = {"files": summaries, "lineups": lineups, "copies": copies}
    save_pool(settings.nfl_data_dir, season, week, platform, contest, data)
    delete_result(settings.nfl_data_dir, season, week, platform, contest)  # pool changed, old results no longer match
    return _info(data, slate_signature(season, week, platform, contest))


class PortfolioRequest(BaseModel):
    size: int = Field(150, ge=1, le=1000)
    max_exposure_pct: float = Field(50.0, gt=0, le=100)
    max_overlap: int = Field(6, ge=0, le=8)


class AnalyzeRequest(BaseModel):
    season: int
    week: int
    platform: str = "DraftKings"
    contest: str = "Classic Main"
    field_size: int = Field(317000, ge=1000)
    weights: dict[str, float] | None = None
    limit: int = Field(300, ge=1, le=2000)
    portfolio: PortfolioRequest | None = None
    flag_settings: FlagSettings = Field(default_factory=FlagSettings)


class PlayerCell(BaseModel):
    slot: str
    name: str
    dk_id: str
    position: str
    team: str
    salary: int
    own: float


class AnalyzedLineup(BaseModel):
    rank: int
    score: float
    percentile: float
    tier: str
    salary: int
    unused: int
    own_sum: float
    players: list[PlayerCell]
    contributions: dict[str, float]
    features: dict[str, float]
    flags: list[LineupFlag] = []


class AnalyzeResult(BaseModel):
    slate_signature: str = ""
    total: int
    unresolved: int
    weights: dict[str, float]
    field_size: int
    top_1pct_entries: int
    tier_counts: dict[str, int]
    warnings: list[str] = []
    exposure: list[ExposureResult] = []
    rows: list[AnalyzedLineup]
    portfolio: list[AnalyzedLineup] | None = None
    # Lineup flags: one summary per flag type (lineups with it), the number of
    # lineups at each severity plus clean ones, and every flagged lineup in
    # rank order (not only the top rows). Lineups that couldn't be matched to
    # the slate come last with rank 0 and no score.
    flag_summary: list[FlagSummary] = []
    flag_counts: dict[str, int] = {}
    flagged: list[AnalyzedLineup] = []


SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]


@router.post("/analyze", response_model=AnalyzeResult)
def analyze(req: AnalyzeRequest) -> AnalyzeResult:
    pool = load_pool(settings.nfl_data_dir, req.season, req.week, req.platform, req.contest)
    if not pool or not pool["lineups"]:
        raise HTTPException(status_code=400, detail="Upload optimizer lineup files first.")
    try:
        week, id_to_name = build_live_week(
            load_salary_csv(settings.nfl_data_dir, req.season, req.week, req.platform, req.contest),
            load_projected_ownership_players(settings.nfl_data_dir, req.season, req.week, req.platform),
            req.season,
            req.week,
        )
        projections_csv = load_projections_csv(settings.nfl_data_dir, req.season, req.week, req.platform)
        lines = team_lines(load_vegas_lines(settings.nfl_data_dir, req.season, req.week))
        stats = scorer.field_stats(week, projections_csv, lines)
    except (SlateError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    sp = scorer.featurize(
        scorer.resolve_pool([[tuple(c) for c in l] for l in pool["lineups"]], week, id_to_name, stats.names), week, stats
    )
    if not len(sp.lineups):
        raise HTTPException(status_code=400, detail="None of the uploaded lineups matched this slate's players.")

    weights = {**scorer.default_weights(), **(req.weights or {})}
    scores, pct, contrib = scorer.score(sp, stats, weights)
    order = np.argsort(-scores)

    # Lineup flags, computed for every uploaded lineup (also ones that couldn't be scored).
    depth_snapshot_path = find_latest_snapshot(settings.snapshots_dir)
    depth_snapshot = load_snapshot(depth_snapshot_path) if depth_snapshot_path else None
    flag_ctx = flag_service.FlagContext(
        pool=week.pool,
        id_to_name=id_to_name,
        injury=flag_service.injury_lookup(depth_snapshot),
        depth=build_depth_rank_lookup(depth_snapshot),
        lines=lines,
        bad_weather_teams=flag_service.bad_weather_teams(load_weather(settings.nfl_data_dir, req.season, req.week)),
        settings=req.flag_settings,
    )
    raw_lineups = [[tuple(c) for c in l] for l in pool["lineups"]]
    flagged_all = flag_service.flag_pool(raw_lineups, pool.get("copies", []), flag_ctx)
    flags_by_key = {f.key: f.flags for f in flagged_all if f.key is not None}

    def row(rank: int, i: int) -> AnalyzedLineup:
        cells = []
        for slot, (name, pid) in zip(SLOTS, sp.lineups[i]):
            p = week.pool[name]
            cells.append(PlayerCell(slot=slot, name=name, dk_id=pid, position=p.position, team=p.team, salary=p.salary, own=round(p.actual_pct, 1)))
        salary = sum(c.salary for c in cells)
        return AnalyzedLineup(
            rank=rank,
            score=round(float(scores[i]), 3),
            percentile=round(float(pct[i]), 2),
            tier=scorer.tier(float(pct[i])),
            salary=salary,
            unused=50000 - salary,
            own_sum=round(sum(c.own for c in cells), 1),
            players=cells,
            contributions={n: round(float(v), 3) for n, v in zip(scorer.ALL_FEATURE_NAMES, contrib[i])},
            features={n: round(float(v), 2) for n, v in zip(scorer.ALL_FEATURE_NAMES, sp.x[i])},
            flags=flags_by_key.get(tuple(sorted(name for name, _pid in sp.lineups[i])), []),
        )

    rows = [row(r + 1, int(i)) for r, i in enumerate(order[: req.limit])]
    tier_counts: dict[str, int] = {}
    for p in pct:
        label = scorer.tier(float(p))
        tier_counts[label] = tier_counts.get(label, 0) + 1

    rank_of = {int(i): r + 1 for r, i in enumerate(order)}
    portfolio = None
    if req.portfolio:
        chosen = scorer.build_portfolio(sp.index, order, req.portfolio.size, req.portfolio.max_exposure_pct, req.portfolio.max_overlap)
        portfolio = [row(rank_of[i], i) for i in chosen]

    def exposure_lineups(indices) -> list[list[LineupPlayer]]:
        out = []
        for i in indices:
            lineup = []
            for slot, (name, _pid) in zip(SLOTS, sp.lineups[int(i)]):
                p = week.pool[name]
                lineup.append(LineupPlayer(slot, name, p.position, p.team, p.salary))
            out.append(lineup)
        return out

    field = {n: p.actual_pct for n, p in week.pool.items()}  # projected ownership
    exposure = [
        build_exposure("all", f"All {len(sp.lineups)} scored", exposure_lineups(range(len(sp.lineups))), field),
        build_exposure("top20", "Top 20 ranked", exposure_lineups(order[:20]), field),
    ]
    if portfolio is not None:
        exposure.append(build_exposure("portfolio", f"Portfolio ({len(portfolio)})", exposure_lineups(chosen), field))

    # Every flagged lineup, scored ones in rank order, unscored ones last.
    index_of_key = {tuple(sorted(name for name, _pid in sp.lineups[i])): i for i in range(len(sp.lineups))}
    flagged_rows: list[AnalyzedLineup] = []
    unscored: list[AnalyzedLineup] = []
    for f in flagged_all:
        if not f.flags:
            continue
        if f.key is not None and f.key in index_of_key:
            i = index_of_key[f.key]
            flagged_rows.append(row(rank_of[i], i))
        else:
            cells = []
            for slot, (raw_name, pid), canon in zip(SLOTS, f.raw, f.names):
                p = week.pool.get(canon) if canon else None
                cells.append(
                    PlayerCell(
                        slot=slot, name=canon or raw_name, dk_id=pid, position=p.position if p else "?",
                        team=p.team if p else "?", salary=p.salary if p else 0, own=round(p.actual_pct, 1) if p else 0.0,
                    )
                )
            salary = sum(c.salary for c in cells)
            unscored.append(
                AnalyzedLineup(
                    rank=0, score=0.0, percentile=0.0, tier="Not scored", salary=salary, unused=50000 - salary,
                    own_sum=round(sum(c.own for c in cells), 1), players=cells, contributions={}, features={}, flags=f.flags,
                )
            )
    flagged_rows.sort(key=lambda r: r.rank)
    flagged_rows.extend(unscored)
    severity_counts = {sev: sum(1 for r in flagged_rows if any(fl.severity == sev for fl in r.flags)) for sev in ("error", "warning", "note")}
    severity_counts["clean"] = len(raw_lineups) - len(flagged_rows)

    warnings = []
    if not stats.extra.has_projections:
        warnings.append("Projections file has no Proj./Ceiling columns -- upside factors are 0 for every lineup.")
    if not stats.extra.has_lines:
        warnings.append("No Vegas lines saved for this week -- game-environment factors are 0 for every lineup.")
    result = AnalyzeResult(
        slate_signature=slate_signature(req.season, req.week, req.platform, req.contest),
        warnings=warnings,
        exposure=exposure,
        total=len(sp.lineups),
        unresolved=sp.unresolved,
        weights=weights,
        field_size=req.field_size,
        top_1pct_entries=int(req.field_size * 0.01),
        tier_counts=tier_counts,
        rows=rows,
        portfolio=portfolio,
        flag_summary=flag_service.summarize(flagged_all),
        flag_counts=severity_counts,
        flagged=flagged_rows,
    )
    save_result(
        settings.nfl_data_dir,
        req.season,
        req.week,
        req.platform,
        req.contest,
        {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "request": req.model_dump(), "result": result.model_dump()},
    )
    return result


class SavedAnalysis(BaseModel):
    saved_at: str
    request: AnalyzeRequest
    result: AnalyzeResult


@router.get("/result", response_model=SavedAnalysis | None)
def saved_result(season: int, week: int, platform: str = "DraftKings", contest: str = "Classic Main"):
    """The last analysis saved for this week/contest, or null."""
    data = load_result(settings.nfl_data_dir, season, week, platform, contest)
    return SavedAnalysis(**data) if data else None


@router.get("/exposure", response_model=ExposureView | None)
def saved_exposure(
    season: int,
    week: int,
    platform: str = "DraftKings",
    contest: str = "Classic Main",
    scope: str = "all",
    position: str = "ALL",
    sort: str = "exposure",
):
    """FLEX counts and player exposure from the last saved analysis (null if
    there is none, or it predates the exposure panel -- re-analyze)."""
    saved = load_result(settings.nfl_data_dir, season, week, platform, contest)
    if not saved or not saved["result"].get("exposure"):
        return None
    results = [ExposureResult(**r) for r in saved["result"]["exposure"]]
    return make_view(results, scope, position, sort, "Field own %")
