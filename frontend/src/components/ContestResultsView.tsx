import { useEffect, useMemo, useState } from "react";
import { fetchContestResultRows, fetchContestTopLineups } from "../api";
import type { ContestResultRow, ContestTopLineup } from "../types";
import { formatExpectedFpts, formatOwnershipPct, formatSalary } from "./playerDisplay";

interface ContestResultsViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

// Same order the contest export's own Lineup field always uses (see
// backend/services/contest_results/contest_standings_parser.py) --
// nothing here re-sorts `players`, this is just documentation of what
// order to expect when reading the table below.
// DST, FLEX, QB, RB, RB, TE, WR, WR, WR

// Sortable columns on the Contest results table below -- % Drafted and
// FPTS come straight off the reference table's own numbers (see
// ContestResultRow), unlike the fixed roster-slot order the per-lineup
// tables intentionally preserve.
type ResultSortKey = "pct_drafted" | "fpts";
type SortDir = "asc" | "desc";

// Position filter chips for the Contest results table -- these are the
// roster-slot tokens the contest export's own Lineup field can produce
// (see _SLOT_TOKEN_RE in contest_standings_parser.py), which is also
// exactly what ContestResultRow.roster_position holds, FLEX included.
const POSITION_FILTER_OPTIONS = ["All", "QB", "RB", "WR", "TE", "FLEX", "DST"] as const;
type PositionFilter = (typeof POSITION_FILTER_OPTIONS)[number];

// Diff = Act Pts - Exp Pts -- green when the player beat their fixed 4x-
// salary expectation, red when they fell short. Reuses Ownership
// Summary's own positive/negative classes (see App.css) for a consistent
// green/red treatment across tabs rather than inventing a second one.
function diffClass(diff: number | null): string {
  if (diff === null || diff === 0) return "";
  return diff > 0 ? "ownership-diff-positive" : "ownership-diff-negative";
}

// Fixed 2-decimal formatting for the Exp Pts / Act Pts / Diff / FPTS
// columns below -- unlike formatExpectedFpts's trailing-zero trim (used
// elsewhere in the app, and still used for the lineup heading's one-off
// points readout), a column of numbers needs every row to show the same
// number of decimal digits so the decimal points line up vertically.
function formatPts(value: number): string {
  return value.toFixed(2);
}

// "6.2x" -- the salary multiplier a player's own Act Pts actually
// realized (Act Pts / (Salary / 1000)), used in the Over 4x Salary/Under
// 4x summary lines below instead of a raw point total, so it reads on
// the same "Nx salary" scale as the Exp Pts/(4x Salary) column itself.
function formatMultiplier(actPts: number, salary: number): string {
  return `${((actPts * 1000) / salary).toFixed(1)}x`;
}

// "WR, TE and RB" / "WR and RB" / "WR" -- natural-language list join used
// by the DST-opponent summary line below (no Oxford comma).
function joinWithAnd(items: string[]): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

// Renders lineup.summary (see contest_results_engine.py's
// _build_lineup_summary) as a plain-language bullet list below each
// lineup's own table -- covers FLEX's true position, game stacks
// (onslaught/overstack), DST/QB team correlation, salary cap usage, and
// each player's own boom/bust + contest-wide ownership/points rank.
function LineupSummaryPanel({ lineup }: { lineup: ContestTopLineup }) {
  const s = lineup.summary;
  const lines: string[] = [];

  if (s.flex_position) {
    lines.push(`${s.flex_position} FLEX`);
  }

  if (s.game_stacks.length === 0) {
    lines.push("No team stacks -- every game in this lineup has at most 1 player");
  } else {
    for (const stack of s.game_stacks) {
      lines.push(
        stack.kind === "onslaught"
          ? `${stack.primary_team} (${stack.primary_positions.join(", ")}) with bring-back ${stack.bringback_team} (${(stack.bringback_positions ?? []).join(", ")})`
          : `${stack.primary_team} (${stack.primary_positions.join(", ")}), no bring-back`
      );
    }
  }

  if (s.dst_team && s.dst_teammates.length > 0) {
    lines.push(`DST (${s.dst_team}) rostered with own-team teammate(s): ${s.dst_teammates.join(", ")}`);
  }
  if (s.dst_team && s.dst_opponent_positions.length > 0) {
    lines.push(`DST (${s.dst_team}) played with opposing team: ${joinWithAnd(s.dst_opponent_positions)}`);
  }

  if (s.qb_player && s.qb_stacked !== null) {
    lines.push(
      s.qb_stacked
        ? `QB ${s.qb_player} stacked with a same-team teammate`
        : `QB ${s.qb_player} played naked`
    );
  }

  lines.push(`Total lineup ownership: ${formatOwnershipPct(lineup.total_pct_drafted)}`);
  lines.push(
    `Spans ${s.distinct_games} game${s.distinct_games === 1 ? "" : "s"} across ${s.distinct_teams} team${
      s.distinct_teams === 1 ? "" : "s"
    }`
  );
  lines.push(
    s.salary_leftover !== null
      ? `${formatSalary(s.salary_leftover)} left under the $50,000 cap`
      : "Salary cap usage unknown -- one or more players didn't match the salary file"
  );

  const boomPlayers = lineup.players.filter((p) => p.boom_bust === "boom");
  const bustPlayers = lineup.players.filter((p) => p.boom_bust === "bust");
  if (boomPlayers.length > 0) {
    lines.push(
      `Over 4x Salary: ${boomPlayers
        .map((p) => `${p.player} (${formatMultiplier(p.act_pts as number, p.salary as number)})`)
        .join(", ")}`
    );
  }
  if (bustPlayers.length > 0) {
    lines.push(
      `Under 4x: ${bustPlayers
        .map((p) => `${p.player} (${formatMultiplier(p.act_pts as number, p.salary as number)})`)
        .join(", ")}`
    );
  }

  const ownershipRanked = lineup.players.filter((p) => p.ownership_rank !== null);
  if (ownershipRanked.length > 0) {
    lines.push(
      `Ownership rank: ${ownershipRanked
        .map((p) => `${p.position ?? p.roster_position} #${p.ownership_rank} ${p.player}`)
        .join(" · ")}`
    );
  }
  const pointsRanked = lineup.players.filter((p) => p.points_rank !== null);
  if (pointsRanked.length > 0) {
    lines.push(
      `Points rank: ${pointsRanked
        .map((p) => `${p.position ?? p.roster_position} #${p.points_rank} ${p.player}`)
        .join(" · ")}`
    );
  }

  return (
    <ul className="contest-results-summary">
      {lines.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  );
}

function LineupTable({ lineup }: { lineup: ContestTopLineup }) {
  return (
    <div className="player-pool-grid-wrap contest-results-lineup-wrap">
      <table className="player-pool-grid contest-results-grid">
        <thead>
          <tr>
            <th>Position</th>
            <th className="player-pool-grid-sticky">Name</th>
            <th>Salary</th>
            <th>% Drafted</th>
            <th>
              Exp Pts
              <br />
              (4x Salary)
            </th>
            <th>Act Pts</th>
            <th>Diff</th>
          </tr>
        </thead>
        <tbody>
          {lineup.players.map((p, i) => (
            <tr key={i}>
              <td>{p.roster_position}</td>
              <td className="player-pool-grid-sticky">{p.player}</td>
              <td className="player-pool-grid-num">{p.salary !== null ? formatSalary(p.salary) : "-"}</td>
              <td className="player-pool-grid-num">{p.pct_drafted !== null ? formatOwnershipPct(p.pct_drafted) : "-"}</td>
              <td className="player-pool-grid-num">{p.exp_pts !== null ? formatPts(p.exp_pts) : "-"}</td>
              <td className="player-pool-grid-num">{p.act_pts !== null ? formatPts(p.act_pts) : "-"}</td>
              <td className={`player-pool-grid-num ${diffClass(p.diff)}`}>
                {p.diff !== null ? formatPts(p.diff) : "-"}
              </td>
            </tr>
          ))}
          <tr className="contest-results-totals-row">
            <td colSpan={2}>Total</td>
            <td className="player-pool-grid-num">{formatSalary(lineup.total_salary)}</td>
            <td className="player-pool-grid-num">{formatOwnershipPct(lineup.total_pct_drafted)}</td>
            <td className="player-pool-grid-num">{formatPts(lineup.total_exp_pts)}</td>
            <td className="player-pool-grid-num">{formatPts(lineup.total_act_pts)}</td>
            <td className={`player-pool-grid-num ${diffClass(lineup.total_diff)}`}>
              {formatPts(lineup.total_diff)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function ContestResultsView({ season, week, platform, contest }: ContestResultsViewProps) {
  const [topN, setTopN] = useState(10);

  const [lineups, setLineups] = useState<ContestTopLineup[] | null>(null);
  const [resultRows, setResultRows] = useState<ContestResultRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Contest results table sorting -- defaults to % Drafted descending
  // (most-owned players first) rather than backend/upload order.
  const [sortKey, setSortKey] = useState<ResultSortKey | null>("pct_drafted");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [positionFilter, setPositionFilter] = useState<PositionFilter>("All");

  function handleSort(key: ResultSortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function sortIndicator(key: ResultSortKey): string {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  }

  const sortedResultRows = useMemo(() => {
    if (!resultRows) return resultRows;
    const filtered =
      positionFilter === "All" ? resultRows : resultRows.filter((row) => row.roster_position === positionFilter);
    if (!sortKey) return filtered;
    const sorted = [...filtered];
    sorted.sort((a, b) => (a[sortKey] - b[sortKey]) * (sortDir === "asc" ? 1 : -1));
    return sorted;
  }, [resultRows, sortKey, sortDir, positionFilter]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetchContestTopLineups(season, week, platform, contest, topN),
      fetchContestResultRows(season, week, platform, contest),
    ])
      .then(([topLineupsResult, resultRowsResult]) => {
        setLineups(topLineupsResult.lineups);
        setResultRows(resultRowsResult.rows);
      })
      .catch((err) => {
        setLineups(null);
        setResultRows(null);
        setError(err instanceof Error ? err.message : "Failed to load contest results");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, contest, topN]);

  const isNotFound = error !== null && (error.includes("uploaded yet") || error.includes("No DK salary file"));

  return (
    <>
      <section className="ownership-section">
        <div className="filters">
          <div className="chip-filter">
            <span className="filter-label">Top lineups</span>
            <input
              type="number"
              min={1}
              value={topN}
              onChange={(e) => setTopN(Math.max(1, Number(e.target.value) || 1))}
              style={{ width: 64 }}
            />
          </div>
        </div>
      </section>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && <p className="hint">{error}</p>}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && lineups && (
        <section className="ownership-section">
          <h2>Top {lineups.length} lineups</h2>
          {lineups.length === 0 ? (
            <p className="hint">No entries found in the uploaded contest standings.</p>
          ) : (
            lineups.map((lineup) => (
              <div key={lineup.rank} className="contest-results-lineup">
                <h3>
                  #{lineup.rank} · {lineup.entry_name} · {formatExpectedFpts(lineup.points)} pts
                </h3>
                <LineupTable lineup={lineup} />
                <LineupSummaryPanel lineup={lineup} />
              </div>
            ))
          )}
        </section>
      )}

      {!loading && !error && sortedResultRows && (
        <section className="ownership-section">
          <div className="player-pool-grid-header">
            <h2>Contest results ({sortedResultRows.length} players)</h2>
          </div>
          <div className="filters">
            <div className="chip-filter">
              <span className="filter-label">Position</span>
              <div className="chip-row">
                {POSITION_FILTER_OPTIONS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    className={`chip${positionFilter === p ? " selected" : ""}`}
                    aria-pressed={positionFilter === p}
                    onClick={() => setPositionFilter(p)}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="player-pool-grid-wrap">
            <table className="player-pool-grid contest-results-grid">
              <thead>
                <tr>
                  <th>Week</th>
                  <th className="player-pool-grid-sticky">Player</th>
                  <th>Salary</th>
                  <th>Roster Position</th>
                  <th className="contest-results-sortable" onClick={() => handleSort("pct_drafted")}>
                    % Drafted{sortIndicator("pct_drafted")}
                  </th>
                  <th className="contest-results-sortable contest-results-fpts-col" onClick={() => handleSort("fpts")}>
                    FPTS{sortIndicator("fpts")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedResultRows.map((row, i) => (
                  <tr key={i}>
                    <td>{row.week}</td>
                    <td className="player-pool-grid-sticky">{row.player}</td>
                    <td className="player-pool-grid-num">{row.salary !== null ? formatSalary(row.salary) : "-"}</td>
                    <td>{row.roster_position}</td>
                    <td className="player-pool-grid-num">{formatOwnershipPct(row.pct_drafted)}</td>
                    <td className="player-pool-grid-num contest-results-fpts-col">{formatPts(row.fpts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
