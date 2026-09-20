import type { ReactNode } from "react";
import { useMemo, useRef, useState, useEffect } from "react";
import { fetchMultipliers } from "../api";
import type { GameOption, MultiplierRow } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { CollapsibleHint } from "./CollapsibleHint";
import {
  POSITION_ORDER,
  formatMultiplier,
  formatPct,
  formatSalary,
  multiplierTier,
  positionRank,
  tierClassName,
} from "./gameLogsShared";

// season/week/platform/contest come from the shared header control (see
// App.tsx), same as every other weekly tab. Like Game Logs/Game Logs
// Against, `contest` only narrows the roster/Game filter down to the
// currently-selected Contest's own DK salary slate -- see
// backend/api/multipliers/multipliers.py's own docstring.
interface MultipliersViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

// How long to wait after the last keystroke in the "Trailing weeks" input
// before refetching -- same debounce idea as Game Logs' own "Weeks of
// history" field.
const TRAILING_WEEKS_DEBOUNCE_MS = 800;

// The exact 5-band vocabulary from the person's own "exact existing 4 color
// bands" answer -- 4 colored bands plus "Below 2.0" for the (uncolored)
// remainder, so every real Multiplier value lands in exactly one tier and
// none are silently excluded from the filter's own option list.
const TIER_OPTIONS = ["4.0+", "3.5-3.99", "3.0-3.49", "2.0-2.99", "Below 2.0"] as const;

function tierLabel(value: number | null): (typeof TIER_OPTIONS)[number] | null {
  if (value === null) return null;
  if (value >= 4) return "4.0+";
  if (value >= 3.5) return "3.5-3.99";
  if (value >= 3) return "3.0-3.49";
  if (value >= 2) return "2.0-2.99";
  return "Below 2.0";
}

type SortDirection = "asc" | "desc";

// Every column is independently sortable, including the dynamically-sized
// Multiplier/W* columns -- rather than a fixed union (like PlayerPoolView's
// own "salary" | "total"), sort fields are plain strings so a
// "mult-w-{weekNumber}" key can address whichever historical week's column
// that is. The base week's own column keeps the plain "multiplier" field
// name (not "mult-w-{baseWeek}") so the default sort ("multiplier",
// descending) keeps working regardless of which absolute week is currently
// the base -- see multiplierForWeek/multiplierWeekNumbers below for how the
// base week ends up as just another entry in this same W-numbered list.
type SortField = string;

// A row's own Multiplier for a given absolute week number -- `weekNum`
// equal to the base week (row.week) reads row.multiplier directly (the
// same value the old, now-removed standalone "Multiplier" column showed);
// anything older looks it up in `trailing` by its own `week` field rather
// than by array index, since the merged column list can skip weeks that
// don't exist (see multiplierWeekNumbers).
function multiplierForWeek(row: MultiplierRow, weekNum: number): number | null {
  if (weekNum === row.week) return row.multiplier;
  return row.trailing.find((t) => t.week === weekNum)?.multiplier ?? null;
}

function getSortValue(row: MultiplierRow, field: SortField): string | number | null {
  switch (field) {
    case "name":
      return row.name;
    case "position":
      return positionRank(row.position);
    case "team":
      return row.team;
    case "week":
      return row.week;
    case "salary":
      return row.salary;
    case "opponent":
      return row.opponent;
    case "game_location":
      return row.game_location;
    case "multiplier":
      return row.multiplier;
    case "fpts":
      return row.fpts;
    case "non_td_fpts":
      return row.non_td_fpts;
    case "non_td_fpts_pct":
      return row.non_td_fpts_pct;
    case "td_fpts":
      return row.td_fpts;
    case "td_fpts_pct":
      return row.td_fpts_pct;
    default:
      if (field.startsWith("mult-w-")) {
        return multiplierForWeek(row, Number(field.slice("mult-w-".length)));
      }
      return null;
  }
}

// Nulls always sort last regardless of direction (a player with no data for
// a given trailing week shouldn't jump to the top of an ascending sort) --
// same convention as OwnershipSummaryView's own compareNullable.
function compareValues(a: string | number | null, b: string | number | null, direction: SortDirection): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  if (typeof a === "number" && typeof b === "number") {
    return direction === "desc" ? b - a : a - b;
  }
  const cmp = String(a).localeCompare(String(b));
  return direction === "desc" ? -cmp : cmp;
}

function SortableTh({
  field,
  label,
  ariaLabel,
  thClassName,
  currentField,
  direction,
  onToggle,
}: {
  field: SortField;
  label: ReactNode;
  // Only needed when `label` isn't a plain string (e.g. the two-line
  // "Multiplier"/"W12" trailing headers) -- otherwise the aria-label would
  // fall back to the raw field key ("trailing-0") instead of readable text.
  ariaLabel?: string;
  // Only the Name column uses this (sticky-left, see .player-pool-grid-sticky)
  // -- every other sortable header here needs no extra class on the <th>
  // itself.
  thClassName?: string;
  currentField: SortField;
  direction: SortDirection;
  onToggle: (field: SortField) => void;
}) {
  const isActive = currentField === field;
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

export function MultipliersView({ season, week, platform, contest }: MultipliersViewProps) {
  const [trailingWeeksInput, setTrailingWeeksInput] = useState("5");
  const [trailingWeeks, setTrailingWeeks] = useState(5);
  const trailingDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [games, setGames] = useState<GameOption[]>([]);
  const [rows, setRows] = useState<MultiplierRow[] | null>(null);
  const [baseWeek, setBaseWeek] = useState<number | null>(null);
  const [resultTrailingWeeks, setResultTrailingWeeks] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Single-select, matching Game Logs/Game Logs Against's own Game filter.
  const [selectedGame, setSelectedGame] = useState<string | null>(null);
  const [selectedPositions, setSelectedPositions] = useState<Set<string>>(new Set());
  const [selectedTeams, setSelectedTeams] = useState<Set<string>>(new Set());
  const [selectedTiers, setSelectedTiers] = useState<Set<string>>(new Set());

  const [sortField, setSortField] = useState<SortField>("multiplier");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchMultipliers(season, week, platform, contest, trailingWeeks)
      .then((result) => {
        setRows(result.rows);
        setGames(result.games);
        setBaseWeek(result.base_week);
        setResultTrailingWeeks(result.trailing_weeks);
      })
      .catch((err) => {
        setRows(null);
        setGames([]);
        setBaseWeek(null);
        setError(err instanceof Error ? err.message : "Failed to load multipliers");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, contest, trailingWeeks]);

  useEffect(() => {
    const timer = trailingDebounce;
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function commitTrailingWeeks(value: string) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) {
      setTrailingWeeks(Math.floor(parsed));
    } else {
      setTrailingWeeksInput(String(trailingWeeks));
    }
  }

  function handleTrailingWeeksChange(value: string) {
    setTrailingWeeksInput(value);
    if (trailingDebounce.current) clearTimeout(trailingDebounce.current);
    trailingDebounce.current = setTimeout(() => {
      trailingDebounce.current = null;
      commitTrailingWeeks(value);
    }, TRAILING_WEEKS_DEBOUNCE_MS);
  }

  function handleTrailingWeeksBlur() {
    if (trailingDebounce.current) {
      clearTimeout(trailingDebounce.current);
      trailingDebounce.current = null;
    }
    commitTrailingWeeks(trailingWeeksInput);
  }

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDirection((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  }

  const gameByKey = useMemo(() => new Map(games.map((g) => [g.key, g])), [games]);

  // Built from the full unfiltered row set, same "independent filters"
  // convention as every other tab's chip rows.
  const teamOptions = useMemo(() => {
    const teams = new Set<string>();
    for (const row of rows ?? []) teams.add(row.team);
    return [...teams].sort();
  }, [rows]);

  const filteredRows = useMemo(() => {
    const selectedGameTeams = selectedGame ? (gameByKey.get(selectedGame)?.teams ?? []) : null;
    return (rows ?? []).filter((row) => {
      if (selectedGameTeams && !selectedGameTeams.includes(row.team)) return false;
      if (selectedPositions.size > 0 && !selectedPositions.has(row.position)) return false;
      if (selectedTeams.size > 0 && !selectedTeams.has(row.team)) return false;
      if (selectedTiers.size > 0) {
        const tier = tierLabel(row.multiplier);
        if (tier === null || !selectedTiers.has(tier)) return false;
      }
      return true;
    });
  }, [rows, selectedGame, selectedPositions, selectedTeams, selectedTiers, gameByKey]);

  const sortedRows = useMemo(() => {
    return [...filteredRows].sort((a, b) =>
      compareValues(getSortValue(a, sortField), getSortValue(b, sortField), sortDirection)
    );
  }, [filteredRows, sortField, sortDirection]);

  // The full set of "Multiplier W*" columns to render -- the base week's
  // own multiplier (previously a separate, unlabeled "Multiplier" column)
  // plus its trailing history, merged into ONE uniformly-labeled list and
  // sorted most-recent-first. Candidates below week 1 (nothing existed
  // before the season started) are dropped rather than shown as an empty
  // column, and the merged list is capped to the "Weeks to show" count
  // (resultTrailingWeeks) -- e.g. week 7 with the default 5 has candidates
  // {6,5,4,3,2,1}, caps to the 5 most recent {6,5,4,3,2}, dropping week 1.
  // Derived from the API response's own base_week/trailing_weeks rather
  // than the (possibly still debouncing) input field, so headers never show
  // a week number the currently-loaded rows don't actually have data for.
  const multiplierWeekNumbers = useMemo(() => {
    if (baseWeek === null || baseWeek < 1) return [];
    const candidates = [baseWeek, ...Array.from({ length: resultTrailingWeeks }, (_, i) => baseWeek - 1 - i)];
    return candidates.filter((w) => w >= 1).slice(0, resultTrailingWeeks);
  }, [baseWeek, resultTrailingWeeks]);

  // Selected week 1 has no base week at all (base_week = week - 1 = 0) --
  // there's nothing to review yet, so this short-circuits the filters/table
  // entirely in favor of a plain explanatory message rather than an empty
  // grid or a misleading "no players match the current filters."
  const noPriorWeek = baseWeek !== null && baseWeek < 1;

  const isNotFound = error !== null && error.includes("No DK Players tracker started yet");

  return (
    <>
      <CollapsibleHint
        items={[
          `Reviews the base week -- always last week (week ${week} - 1${
            baseWeek !== null ? ` = week ${baseWeek}` : ""
          }) -- this tab is a "how did last week's pricing work out" review, not a preview of the upcoming week.`,
          "Salary/FPTS/Non-TD/TD come from the DK Players tracker; Opponent/GameLoc come from the Schedule file.",
          "Each Multiplier/W{n} column is that player's own Multiplier for week n -- the leftmost is always the base week itself, followed by however many prior weeks exist, most recent first. Change the count below to show more or fewer weeks (default 5); early-season weeks simply show fewer columns since there isn't more history yet.",
          "Multiplier coloring: dark green 4.0+, light green 3.5-3.99, dark gold 3.0-3.49, light gold 2.0-2.99, no color below 2.0 -- applied to every Multiplier/W* column.",
          "Players are scoped to the currently selected Contest's own DK salary slate.",
          "A non-DST player's base week is hidden entirely if their FPTS was exactly 0 that week; a trailing week's own Multiplier still shows even if that week was a real 0 (DST always shows regardless).",
          "Click any column header to sort by it; click again to flip direction. Defaults to Multiplier, highest first.",
        ]}
      />

      {noPriorWeek && (
        <p className="hint">
          Week {week} has no prior week to review yet -- Multipliers always reviews the week before the one
          selected, and week {week} is the first week of the season.
        </p>
      )}

      {!noPriorWeek && (
      <>
      <div className="filters">
        <div className="chip-filter">
          <span className="filter-label">Game</span>
          <div className="chip-row">
            <button
              type="button"
              className={`chip${selectedGame === null ? " selected" : ""}`}
              aria-pressed={selectedGame === null}
              onClick={() => setSelectedGame(null)}
            >
              All
            </button>
            {games.map((g) => (
              <button
                key={g.key}
                type="button"
                className={`chip${selectedGame === g.key ? " selected" : ""}`}
                aria-pressed={selectedGame === g.key}
                onClick={() => setSelectedGame((current) => (current === g.key ? null : g.key))}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>
        <ChipMultiSelect
          label="Position"
          options={[...POSITION_ORDER]}
          selected={selectedPositions}
          onChange={setSelectedPositions}
        />
        <ChipMultiSelect label="Team" options={teamOptions} selected={selectedTeams} onChange={setSelectedTeams} />
        <ChipMultiSelect
          label="Multiplier Tier"
          options={[...TIER_OPTIONS]}
          selected={selectedTiers}
          onChange={setSelectedTiers}
        />
        <label className="game-logs-lookback-field">
          Weeks to show
          <input
            type="number"
            min={1}
            max={17}
            value={trailingWeeksInput}
            onChange={(e) => handleTrailingWeeksChange(e.target.value)}
            onBlur={handleTrailingWeeksBlur}
          />
        </label>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && <p className="hint">{error}</p>}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && rows !== null && sortedRows.length === 0 && (
        <p className="hint">No players match the current filters.</p>
      )}

      {!loading && !error && sortedRows.length > 0 && (
        <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
          <table className="player-pool-grid ownership-summary-grid multipliers-grid">
            <thead>
              <tr>
                <SortableTh
                  field="name"
                  label="Name"
                  thClassName="player-pool-grid-sticky player-selection-name-col"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="position"
                  label="Position"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh field="team" label="Team" currentField={sortField} direction={sortDirection} onToggle={toggleSort} />
                <SortableTh field="week" label="Week" currentField={sortField} direction={sortDirection} onToggle={toggleSort} />
                <SortableTh
                  field="salary"
                  label="Salary"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="opponent"
                  label="Opponent"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="game_location"
                  label="GameLoc"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh field="fpts" label="FPTS" currentField={sortField} direction={sortDirection} onToggle={toggleSort} />
                <SortableTh
                  field="non_td_fpts"
                  label={
                    <>
                      Non-TD
                      <br />
                      FPTS
                    </>
                  }
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="non_td_fpts_pct"
                  label={
                    <>
                      Non-TD
                      <br />%
                    </>
                  }
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="td_fpts"
                  label={
                    <>
                      TD
                      <br />
                      FPTS
                    </>
                  }
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh field="td_fpts_pct" label="TD %" currentField={sortField} direction={sortDirection} onToggle={toggleSort} />
                {multiplierWeekNumbers.map((w) => (
                  <SortableTh
                    key={`mult-w-${w}`}
                    field={w === baseWeek ? "multiplier" : `mult-w-${w}`}
                    label={
                      <>
                        Multiplier
                        <br />W{w}
                      </>
                    }
                    ariaLabel={`Multiplier W${w}`}
                    currentField={sortField}
                    direction={sortDirection}
                    onToggle={toggleSort}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr key={`${row.name}-${row.position}`}>
                  <td className="player-pool-grid-sticky player-selection-name-col">{row.name}</td>
                  <td>{row.position}</td>
                  <td>{row.team}</td>
                  <td className="player-pool-grid-num">{row.week}</td>
                  <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
                  <td>{row.opponent ?? "-"}</td>
                  <td>{row.game_location ?? "-"}</td>
                  <td className="player-pool-grid-num">{row.fpts.toFixed(1)}</td>
                  <td className="player-pool-grid-num">{row.non_td_fpts.toFixed(1)}</td>
                  <td className="player-pool-grid-num">{formatPct(row.non_td_fpts_pct)}</td>
                  <td className="player-pool-grid-num">{row.td_fpts.toFixed(1)}</td>
                  <td className="player-pool-grid-num">{formatPct(row.td_fpts_pct)}</td>
                  {multiplierWeekNumbers.map((w) => {
                    const value = multiplierForWeek(row, w);
                    return (
                      <td key={`mult-w-${w}`} className={`player-pool-grid-num ${tierClassName(multiplierTier(value)) ?? ""}`}>
                        {formatMultiplier(value)}
                      </td>
                    );
                  })}
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
