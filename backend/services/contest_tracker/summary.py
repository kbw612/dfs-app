"""ROI and totals for the Results Tracker. ROI = (won - cost) / cost, over the
weeks actually played only."""

from __future__ import annotations

from backend.schemas.contest_tracker.contest_tracker import ContestSummary, ContestTrackerResult, TrackerFile


def _roi(cost: float, won: float) -> float | None:
    return round((won - cost) / cost * 100.0, 2) if cost > 0 else None


def summarize(data: TrackerFile) -> ContestTrackerResult:
    contests: list[ContestSummary] = []
    week_net: dict[int, float] = {}
    for c in data.contests:
        entries = sorted((e for e in data.entries if e.contest_id == c.id), key=lambda e: e.week)
        cost = round(sum(e.cost for e in entries), 2)
        won = round(sum(e.won for e in entries), 2)
        contests.append(
            ContestSummary(id=c.id, name=c.name, entries=entries, cost=cost, won=won, roi_pct=_roi(cost, won), played=len(entries))
        )
        for e in entries:
            week_net[e.week] = round(week_net.get(e.week, 0.0) + e.won - e.cost, 2)
    total_cost = round(sum(c.cost for c in contests), 2)
    total_won = round(sum(c.won for c in contests), 2)
    weeks = [e.week for c in contests for e in c.entries]
    return ContestTrackerResult(
        season=data.season,
        weeks_elapsed=max(weeks) if weeks else 0,
        contests=contests,
        week_net=dict(sorted(week_net.items())),
        total_cost=total_cost,
        total_won=total_won,
        total_roi_pct=_roi(total_cost, total_won),
        net=round(total_won - total_cost, 2),
    )
