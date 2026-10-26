"""
Upside and game-environment factors for the Lineup Analyzer. These need data
the 2025 history lacks (the projections file's Proj./Ceiling columns and the
Vegas lines), so their default weights are fitted on 2026 weeks 1-6 instead
(see extra_weights.json) and are lightly regularized priors, not 2025 results.

Features (EXTRA_FEATURE_NAMES), all per lineup:
- proj_sum: sum of the 9 players' projected points (file's "Proj." column).
- ceiling_sum: sum of their "Ceiling" values.
- qb_game_total: over/under of the QB's game.
- avg_team_implied: mean implied team total across the 8 offensive players.
- dst_opp_implied: implied total of the team the lineup's DST faces (lower is
  better for the DST).

A player missing from the projections file gets the lowest Proj./Ceiling listed
for his position (the file lists only the relevant players). A team without a
Vegas line gets the slate's average. If the slate has no Proj./Ceiling columns
or no lines, the affected features are 0 for every lineup, and the caller shows
a warning.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.schemas.vegas_lines.vegas_lines import VegasLinesSnapshot
from backend.services.lineup_analyzer.history_loader import HistoricalWeek
from backend.services.ownership.parsing import normalize_team_abbrev

EXTRA_FEATURE_NAMES = ["proj_sum", "ceiling_sum", "qb_game_total", "avg_team_implied", "dst_opp_implied"]
_WEIGHTS_PATH = Path(__file__).with_name("extra_weights.json")


def default_extra_weights() -> dict[str, float]:
    if not _WEIGHTS_PATH.exists():
        return {n: 0.0 for n in EXTRA_FEATURE_NAMES}
    data = json.loads(_WEIGHTS_PATH.read_text())
    return dict(zip(data["features"], data["weights"]))


@dataclass
class ExtraPool:
    proj: np.ndarray
    ceiling: np.ndarray
    team_implied: np.ndarray  # implied total of the player's own team
    opp_implied: np.ndarray  # implied total of the team he faces
    game_total: np.ndarray
    has_projections: bool
    has_lines: bool


def _num(text: str | None) -> float | None:
    try:
        return float((text or "").replace(",", "").replace("$", "").replace("%", "").strip())
    except ValueError:
        return None


def parse_proj_ceiling(csv_text: str | None) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    """({name: (proj, ceiling)} for non-DST, {team: (proj, ceiling)} for DST)."""
    by_name: dict[str, tuple[float, float]] = {}
    by_dst_team: dict[str, tuple[float, float]] = {}
    if not csv_text:
        return by_name, by_dst_team
    for row in csv.DictReader(io.StringIO(csv_text)):
        proj, ceil = _num(row.get("Proj.")), _num(row.get("Ceiling"))
        if proj is None or ceil is None:
            continue
        name = (row.get("Player") or "").strip()
        if (row.get("Position") or "").strip() == "DST":
            try:
                by_dst_team[normalize_team_abbrev(row.get("Team") or "")] = (proj, ceil)
            except ValueError:
                continue
        elif name:
            by_name[name] = (proj, ceil)
    return by_name, by_dst_team


def team_lines(snapshot: VegasLinesSnapshot | None) -> dict[str, tuple[float, float, float]]:
    """{team: (own implied, opponent implied, game total)} from the latest
    scrape; games with a missing figure are skipped."""
    out: dict[str, tuple[float, float, float]] = {}
    if snapshot is None:
        return out
    for g in snapshot.games:
        cur = g.current
        if not (g.home_team and g.away_team and cur.over_under and cur.home_implied_total and cur.away_implied_total):
            continue
        out[g.home_team] = (cur.home_implied_total, cur.away_implied_total, cur.over_under)
        out[g.away_team] = (cur.away_implied_total, cur.home_implied_total, cur.over_under)
    return out


def build_extra_pool(
    week: HistoricalWeek,
    names: list[str],
    projections_csv: str | None,
    lines: dict[str, tuple[float, float, float]],
) -> ExtraPool:
    by_name, by_dst = parse_proj_ceiling(projections_csv)
    floor: dict[str, tuple[float, float]] = {}
    for n, (pr, ce) in by_name.items():
        pos = week.pool[n].position if n in week.pool else None
        if pos:
            f = floor.get(pos, (pr, ce))
            floor[pos] = (min(f[0], pr), min(f[1], ce))
    if by_dst:
        floor["DST"] = (min(v[0] for v in by_dst.values()), min(v[1] for v in by_dst.values()))
    avg_line = tuple(np.mean(list(lines.values()), axis=0)) if lines else (0.0, 0.0, 0.0)
    proj, ceil, own_i, opp_i, tot = [], [], [], [], []
    for n in names:
        p = week.pool[n]
        got = by_dst.get(p.team) if p.position == "DST" else by_name.get(n)
        pr, ce = got or floor.get(p.position, (0.0, 0.0))
        line = lines.get(p.team, avg_line)
        proj.append(pr)
        ceil.append(ce)
        own_i.append(line[0])
        opp_i.append(line[1])
        tot.append(line[2])
    return ExtraPool(
        np.array(proj), np.array(ceil), np.array(own_i), np.array(opp_i), np.array(tot), bool(by_name), bool(lines)
    )


def extra_feature_matrix(lineups: np.ndarray, extra: ExtraPool) -> np.ndarray:
    qb, dst, offense = lineups[:, 0], lineups[:, 8], lineups[:, :8]
    cols = [
        extra.proj[lineups].sum(axis=1) if extra.has_projections else np.zeros(len(lineups)),
        extra.ceiling[lineups].sum(axis=1) if extra.has_projections else np.zeros(len(lineups)),
        extra.game_total[qb] if extra.has_lines else np.zeros(len(lineups)),
        extra.team_implied[offense].mean(axis=1) if extra.has_lines else np.zeros(len(lineups)),
        extra.opp_implied[dst]
        if extra.has_lines
        else np.zeros(len(lineups)),
    ]
    return np.column_stack(cols).astype(np.float64)
