import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchDstTrends } from "../api";
import type { DstTrendTeamRow } from "../types";
import { CollapsibleHint } from "./CollapsibleHint";
import { formatCount, formatDecimal } from "./gameLogsShared";

// season/week come from the shared header control (see App.tsx), same as
// every other weekly tab. No platform/contest props -- these are league-wide
// team stats straight off the DST FantasyData file, not scoped to a DK
// salary slate (see backend/api/dst_trends/dst_trends.py's own docstring).
interface DstTrendsViewProps {
  season: number;
  week: number;
}

// How long to wait after the last keystroke in the "Weeks to show" input
// before refetching -- same debounce idea as Multipliers' own trailing-weeks
// field.
const WINDOW_WEEKS_DEBOUNCE_MS = 800;

// One row per team (all 32 show up on both sides -- see build_dst_trend_
// leaderboards' own docstring: every team with a game in the window gets a
// row on both the forcing and allowing side, with the SAME games count on
// both, since it's the same team's own games either way), merging the
// backend's separate forcing/allowing arrays into a single wide row instead
// of two separately-ranked tables -- see mergeDstTrendRows below.
interface CombinedDstTrendRow {
  team: string;
  games: number;
  sacksForced: number;
  sacksPerGameForced: number;
  takeawaysForced: number;
  takeawaysPerGameForced: number;
  sacksAllowed: number;
  sacksPerGameAllowed: number;
  takeawaysAllowed: number;
  takeawaysPerGameAllowed: number;
}

// Merges the backend's own forcing/allowing arrays (each already one row
// per team) into one row per team keyed by team name. Falls back to 0s for
// a side missing a team entirely -- shouldn't happen in practice (every
// team with any game in the window gets a row on both sides, per the
// engine's own docstring) but keeps this defensive rather than assuming.
function mergeDstTrendRows(forcing: DstTrendTeamRow[], allowing: DstTrendTeamRow[]): CombinedDstTrendRow[] {
  const forcingByTeam = new Map(forcing.map((r) => [r.team, r]));
  const allowingByTeam = new Map(allowing.map((r) => [r.team, r]));
  const teams = new Set([...forcingByTeam.keys(), ...allowingByTeam.keys()]);
  return [...teams].map((team) => {
    const f = forcingByTeam.get(team);
    const a = allowingByTeam.get(team);
    return {
      team,
      games: f?.games ?? a?.games ?? 0,
      sacksForced: f?.sacks ?? 0,
      sacksPerGameForced: f?.sacks_per_game ?? 0,
      takeawaysForced: f?.takeaways ?? 0,
      takeawaysPerGameForced: f?.takeaways_per_game ?? 0,
      sacksAllowed: a?.sacks ?? 0,
      sacksPerGameAllowed: a?.sacks_per_game ?? 0,
      takeawaysAllowed: a?.takeaways ?? 0,
      takeawaysPerGameAllowed: a?.takeaways_per_game ?? 0,
    };
  });
}

type SortField =
  | "team"
  | "games"
  | "sacksForced"
  | "sacksPerGameForced"
  | "takeawaysForced"
  | "takeawaysPerGameForced"
  | "sacksAllowed"
  | "sacksPerGameAllowed"
  | "takeawaysAllowed"
  | "takeawaysPerGameAllowed";

type SortDirection = "asc" | "desc";

function getSortValue(row: CombinedDstTrendRow, field: SortField): string | number {
  return row[field];
}

function compareValues(a: string | number, b: string | number, direction: SortDirection): number {
  if (typeof a === "number" && typeof b === "number") {
    return direction === "desc" ? b - a : a - b;
  }
  const cmp = String(a).localeCompare(String(b));
  return direction === "desc" ? -cmp : cmp;
}

// The exact compound ranking each of the two old, now-merged leaderboard
// panels used to show by default (see backend/services/dst_trends/
// dst_trends_engine.py's own sort key) -- Sacks/Game first, then total
// Sacks, then Takeaways/Game, then total Takeaways, all descending. A plain
// single-column header click can't reproduce this (that's just one field),
// so these two named presets -- surfaced as chips above the grid -- are
// what "jump back to the Forcing/Allowing leaderboard order" now means.
type CompoundSort = "forcing" | "allowing";

function compoundCompare(a: CombinedDstTrendRow, b: CombinedDstTrendRow, which: CompoundSort): number {
  if (which === "forcing") {
    return (
      b.sacksPerGameForced - a.sacksPerGameForced ||
      b.sacksForced - a.sacksForced ||
      b.takeawaysPerGameForced - a.takeawaysPerGameForced ||
      b.takeawaysForced - a.takeawaysForced
    );
  }
  return (
    b.sacksPerGameAllowed - a.sacksPerGameAllowed ||
    b.sacksAllowed - a.sacksAllowed ||
    b.takeawaysPerGameAllowed - a.takeawaysPerGameAllowed ||
    b.takeawaysAllowed - a.takeawaysAllowed
  );
}

// Same sortable-header pattern as MultipliersView's own SortableTh
// (duplicated here, not shared, per this codebase's convention for small
// per-tab UI helpers) -- clicking a header always drops out of whichever
// compound-sort chip is active (see the component's own toggleSort).
function SortableTh({
  field,
  label,
  ariaLabel,
  thClassName,
  currentField,
  direction,
  compoundActive,
  onToggle,
}: {
  field: SortField;
  label: ReactNode;
  ariaLabel?: string;
  thClassName?: string;
  currentField: SortField;
  direction: SortDirection;
  compoundActive: boolean;
  onToggle: (field: SortField) => void;
}) {
  const isActive = !compoundActive && currentField === field;
  const plainLabel = ariaLabel ?? (typeof label === "string" ? label : field);
  return (
    <th className={thClassName} aria-sort={isActive ? (direction === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        className="player-pool-sort-header player-pool-sort-header-stacked"
        onClick={() => onToggle(field)}
        aria-label={
          isActive
            ? `Sort by ${plainLabel} ${direction === "asc" ? "descending" : "ascending"}`
            : `Sort by ${plainLabel}`
        }
      >
        {label}
        <span className="player-pool-sort-icon" aria-hidden="true">
          {isActive ? (direction === "asc" ? "▲" : "▼") : "⇅"}
        </span>
      </button>
    </th>
  );
}

export function DstTrendsView({ season, week }: DstTrendsViewProps) {
  const [windowWeeksInput, setWindowWeeksInput] = useState("5");
  const [windowWeeks, setWindowWeeks] = useState(5);
  const windowDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [forcing, setForcing] = useState<DstTrendTeamRow[] | null>(null);
  const [allowing, setAllowing] = useState<DstTrendTeamRow[] | null>(null);
  const [throughWeek, setThroughWeek] = useState<number | null>(null);
  const [resultWindowWeeks, setResultWindowWeeks] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Defaults to the Forcing preset -- the same order the old Forcing panel
  // (rendered first, above Allowing) showed on load.
  const [compoundSort, setCompoundSort] = useState<CompoundSort | null>("forcing");
  const [sortField, setSortField] = useState<SortField>("sacksPerGameForced");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchDstTrends(season, week, windowWeeks)
      .then((result) => {
        setForcing(result.forcing);
        setAllowing(result.allowing);
        setThroughWeek(result.through_week);
        setResultWindowWeeks(result.window_weeks);
      })
      .catch((err) => {
        setForcing(null);
        setAllowing(null);
        setThroughWeek(null);
        setError(err instanceof Error ? err.message : "Failed to load DST trends");
      })
      .finally(() => setLoading(false));
  }, [season, week, windowWeeks]);

  useEffect(() => {
    const timer = windowDebounce;
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function commitWindowWeeks(value: string) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) {
      setWindowWeeks(Math.floor(parsed));
    } else {
      setWindowWeeksInput(String(windowWeeks));
    }
  }

  function handleWindowWeeksChange(value: string) {
    setWindowWeeksInput(value);
    if (windowDebounce.current) clearTimeout(windowDebounce.current);
    windowDebounce.current = setTimeout(() => {
      windowDebounce.current = null;
      commitWindowWeeks(value);
    }, WINDOW_WEEKS_DEBOUNCE_MS);
  }

  function handleWindowWeeksBlur() {
    if (windowDebounce.current) {
      clearTimeout(windowDebounce.current);
      windowDebounce.current = null;
    }
    commitWindowWeeks(windowWeeksInput);
  }

  function toggleSort(field: SortField) {
    setCompoundSort(null);
    if (sortField === field) {
      setSortDirection((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  }

  const rows = useMemo(() => {
    if (forcing === null || allowing === null) return null;
    return mergeDstTrendRows(forcing, allowing);
  }, [forcing, allowing]);

  const sortedRows = useMemo(() => {
    if (rows === null) return [];
    if (compoundSort !== null) {
      return [...rows].sort((a, b) => compoundCompare(a, b, compoundSort));
    }
    return [...rows].sort((a, b) => compareValues(getSortValue(a, sortField), getSortValue(b, sortField), sortDirection));
  }, [rows, compoundSort, sortField, sortDirection]);

  const isNotFound = error !== null && error.includes("No DST weekly stats scraped yet");
  const noPriorWeek = throughWeek !== null && throughWeek < 1;

  return (
    <>
      <CollapsibleHint
        items={[
          `Reviews the trailing window of completed weeks -- through week ${week} - 1${
            throughWeek !== null ? ` = week ${throughWeek}` : ""
          }, going back "Weeks to show" weeks (currently ${resultWindowWeeks}, default 5) -- same "review last week and back" convention as Multipliers' own base week.`,
          "Built entirely from the DST FantasyData file: each DST's own row names the offense it played that week (Opponent), so one file gives both sides of the sack/turnover matchup -- no join against QB/RB/WR/TE files needed.",
          "One row per team, with both sides of that team's own trend: Forced (their DST's own sacks and takeaways -- Def Int + Fumble Rec -- generated) and Allowed (sacks and turnovers their own offense gave up to the DST they played that week).",
          "Click any column header to sort by just that column (highest first, click again to flip direction). Use the Forcing/Allowing chips above the grid to jump back to the exact ranking the old separate leaderboards showed -- Sacks/Game first, then total Sacks, then Takeaways/Game, then total Takeaways, all descending -- which a single-column header click can't reproduce on its own.",
          "This is Phase 1 -- team-level trends only, not yet cross-referenced against this week's actual matchups (a hot DST here isn't necessarily playing a leaky offense this week).",
        ]}
      />

      {noPriorWeek && (
        <p className="hint">
          Week {week} has no prior week to review yet -- DST/Off Trends always reviews the week before the one selected,
          and week {week} is the first week of the season.
        </p>
      )}

      {!noPriorWeek && (
        <>
          <div className="filters">
            <div className="chip-filter">
              <span className="filter-label">Sort by</span>
              <div className="chip-row">
                <button
                  type="button"
                  className={`chip${compoundSort === "forcing" ? " selected" : ""}`}
                  aria-pressed={compoundSort === "forcing"}
                  onClick={() => setCompoundSort("forcing")}
                >
                  Top Forcing
                </button>
                <button
                  type="button"
                  className={`chip${compoundSort === "allowing" ? " selected" : ""}`}
                  aria-pressed={compoundSort === "allowing"}
                  onClick={() => setCompoundSort("allowing")}
                >
                  Top Allowing
                </button>
              </div>
            </div>
            <label className="game-logs-lookback-field">
              Weeks to show
              <input
                type="number"
                min={1}
                max={17}
                value={windowWeeksInput}
                onChange={(e) => handleWindowWeeksChange(e.target.value)}
                onBlur={handleWindowWeeksBlur}
              />
            </label>
          </div>

          {loading && <p className="hint">Loading…</p>}
          {!loading && error && isNotFound && <p className="hint">{error}</p>}
          {!loading && error && !isNotFound && <p className="error">{error}</p>}

          {!loading && !error && rows !== null && rows.length === 0 && (
            <p className="hint">No DST data available for this window yet.</p>
          )}

          {!loading && !error && rows !== null && rows.length > 0 && (
            <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
              <table className="player-pool-grid ownership-summary-grid">
                <thead>
                  <tr>
                    <SortableTh
                      field="team"
                      label="Team"
                      thClassName="player-pool-grid-sticky player-selection-name-col"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="games"
                      label="Games"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="sacksForced"
                      label={
                        <>
                          Sacks
                          <br />
                          Forced
                        </>
                      }
                      ariaLabel="Sacks Forced"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="sacksPerGameForced"
                      label={
                        <>
                          Sacks/G
                          <br />
                          Forced
                        </>
                      }
                      ariaLabel="Sacks Per Game Forced"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="takeawaysForced"
                      label={
                        <>
                          Takeaways
                          <br />
                          Forced
                        </>
                      }
                      ariaLabel="Takeaways Forced"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="takeawaysPerGameForced"
                      label={
                        <>
                          Takeaways/G
                          <br />
                          Forced
                        </>
                      }
                      ariaLabel="Takeaways Per Game Forced"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="sacksAllowed"
                      label={
                        <>
                          Sacks
                          <br />
                          Allowed
                        </>
                      }
                      ariaLabel="Sacks Allowed"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="sacksPerGameAllowed"
                      label={
                        <>
                          Sacks/G
                          <br />
                          Allowed
                        </>
                      }
                      ariaLabel="Sacks Per Game Allowed"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="takeawaysAllowed"
                      label={
                        <>
                          Takeaways
                          <br />
                          Allowed
                        </>
                      }
                      ariaLabel="Takeaways Allowed"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                    <SortableTh
                      field="takeawaysPerGameAllowed"
                      label={
                        <>
                          Takeaways/G
                          <br />
                          Allowed
                        </>
                      }
                      ariaLabel="Takeaways Per Game Allowed"
                      currentField={sortField}
                      direction={sortDirection}
                      compoundActive={compoundSort !== null}
                      onToggle={toggleSort}
                    />
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row) => (
                    <tr key={row.team}>
                      <td className="player-pool-grid-sticky player-selection-name-col">{row.team}</td>
                      <td className="player-pool-grid-num">{formatCount(row.games)}</td>
                      <td className="player-pool-grid-num">{formatCount(row.sacksForced)}</td>
                      <td className="player-pool-grid-num">{formatDecimal(row.sacksPerGameForced)}</td>
                      <td className="player-pool-grid-num">{formatCount(row.takeawaysForced)}</td>
                      <td className="player-pool-grid-num">{formatDecimal(row.takeawaysPerGameForced)}</td>
                      <td className="player-pool-grid-num">{formatCount(row.sacksAllowed)}</td>
                      <td className="player-pool-grid-num">{formatDecimal(row.sacksPerGameAllowed)}</td>
                      <td className="player-pool-grid-num">{formatCount(row.takeawaysAllowed)}</td>
                      <td className="player-pool-grid-num">{formatDecimal(row.takeawaysPerGameAllowed)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
