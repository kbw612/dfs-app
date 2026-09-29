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

// A player needs at least this many high weeks (not just 1) to count as a
// "repeat performer" for the watchlist panel below the main grid -- one
// good week is just a good week, not a trend.
const REPEAT_PERFORMER_MIN_HIGH_WEEKS = 2;

// Same idea for the Breakout Watch panel, but on the non-TD Multiplier
// sequence: the person's own "not over 1 week -- 2 or more weeks" framing
// for a breakout candidate (see this tab's own hint text) -- one good
// volume week doesn't distinguish a real role from a one-off game script.
const BREAKOUT_WATCH_MIN_HIGH_WEEKS = 2;

// A "high" non-TD-multiplier week for Breakout Watch purposes is a fixed
// band -- 2.5 up to (not including) 4.0 -- rather than a >= cutoff like
// Repeat Performers' own "High threshold" field. This is deliberately NOT
// tied to that adjustable field: a player already averaging 4.0+ isn't a
// breakout WATCH candidate, they're already there (that's what Repeat
// Performers is for) -- this panel is specifically for the players still
// building toward it.
const BREAKOUT_WATCH_NON_TD_MULT_MIN = 2.5;
const BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE = 4.0;

function inBreakoutWatchBand(value: number): boolean {
  return value >= BREAKOUT_WATCH_NON_TD_MULT_MIN && value < BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE;
}

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

// Same lookup, for the non-TD Multiplier -- feeds Breakout Watch's own
// per-week W* columns, mirroring multiplierForWeek above exactly.
function nonTdMultiplierForWeek(row: MultiplierRow, weekNum: number): number | null {
  if (weekNum === row.week) return row.non_td_multiplier;
  return row.trailing.find((t) => t.week === weekNum)?.non_td_multiplier ?? null;
}

// A row's full Multiplier history, most-recent-first: the base week's own
// value, then every trailing week in the order the backend already returns
// them (see MultiplierRow's own docstring). Deliberately NOT capped to
// multiplierWeekNumbers -- that list is only truncated for column-header
// display when early-season weeks run out; the trend metrics below should
// still see every week the backend actually sent (exactly `trailing_weeks`
// of them), which is the same window the "Weeks to show" field already
// controls.
function multiplierSequence(row: MultiplierRow): (number | null)[] {
  return [row.multiplier, ...row.trailing.map((t) => t.multiplier)];
}

// Same shape as multiplierSequence, but reads non_td_multiplier instead --
// feeds the Breakout Watch panel's trend metrics below (see
// BREAKOUT_WATCH_MIN_HIGH_WEEKS's own comment for why non-TD specifically:
// a player's TD-variance-stripped value trend is what actually predicts a
// breakout, since a raw Multiplier can already be "high" purely off one
// touchdown, which is the opposite of what a breakout WATCH wants to find --
// someone whose volume alone is already good and just hasn't scored yet.
function nonTdMultiplierSequence(row: MultiplierRow): (number | null)[] {
  return [row.non_td_multiplier, ...row.trailing.map((t) => t.non_td_multiplier)];
}

// Same shape/ordering as nonTdMultiplierSequence, but reads td_fpts instead
// -- lets Breakout Watch's "high week" check confirm, per week, that the
// week had zero TD FPTS (see isBreakoutWatchHighWeek below), not just the
// base week. null under the same "no tracker row that week" condition as
// every other per-week field here.
function tdFptsSequence(row: MultiplierRow): (number | null)[] {
  return [row.td_fpts, ...row.trailing.map((t) => t.td_fpts)];
}

// How many of `values` (weeks with data at all) count as "high" per
// `isHigh`, out of how many weeks had data -- e.g. {count: 4, total: 6}
// renders as "4/6". Weeks with no tracker row (bye, not yet rostered)
// don't count toward either the numerator or denominator, same "missing
// isn't a zero" convention as every other optional field here. Takes a
// plain values array plus a predicate (rather than a MultiplierRow and a
// single >= threshold) so the same function serves both the raw-Multiplier
// trend (Repeat Performers -- "high" means >= the adjustable High
// threshold field) and the non-TD-Multiplier trend (Breakout Watch --
// "high" means a fixed 2.5-to-under-4.0 band, see
// isBreakoutWatchHighWeek) -- callers pass whichever sequence via
// multiplierSequence/nonTdMultiplierSequence above.
// `isHigh` takes the week's own index alongside its value (not just the
// value) so a caller can cross-reference a second parallel array by that
// same index -- specifically, Breakout Watch's own isBreakoutWatchHighWeek
// below, which also needs that week's td_fpts (from tdFptsSequence) to
// decide "high," not just its non-TD Multiplier. Existing callers that only
// care about the value (Repeat Performers' isHighMultiplier) simply ignore
// the second argument. A week counts toward `total` (has data) whenever its
// own value is non-null, regardless of whether isHigh returns true for it
// -- a TD week still "has data," it just isn't "high."
function highWeeksCount(
  values: (number | null)[],
  isHigh: (value: number, index: number) => boolean
): { count: number; total: number } {
  let count = 0;
  let total = 0;
  values.forEach((v, i) => {
    if (v === null) return;
    total += 1;
    if (isHigh(v, i)) count += 1;
  });
  return { count, total };
}

// The most recent unbroken run of "high" (per `isHigh`) weeks, starting
// from the base week (the first entry in `values`) and walking backward --
// stops at the first week that either has no data or isn't high. Distinct
// from highWeeksCount: a player who was hot 3 weeks ago but cold the last
// 2 has a high count but a streak of 0, which is exactly the distinction
// "who's hot right now" needs that a plain count can't make. Same
// values-array-plus-predicate parameterization as highWeeksCount above.
function currentStreak(values: (number | null)[], isHigh: (value: number, index: number) => boolean): number {
  let streak = 0;
  for (let i = 0; i < values.length; i++) {
    const value = values[i];
    if (value === null || !isHigh(value, i)) break;
    streak += 1;
  }
  return streak;
}

// The middle value of whatever weeks have data (average of the two middle
// values when there's an even count) -- null (not 0) if the player has no
// history at all yet, same "no data" convention as every other optional
// numeric field on this tab. Median rather than mean specifically because
// one huge week (a 6.0x mixed in with a run of 2.0-2.5x weeks) would
// otherwise drag the average up into "looks like a repeat performer" (or,
// for the non-TD sequence, "looks like a breakout candidate") territory
// for a player who really just had one fluke game -- median is far less
// sensitive to that single outlier, which matters more here than mean's
// usual advantages. Same values-array parameterization as the two above.
function medianOf(values: (number | null)[]): number | null {
  const withData = values.filter((v): v is number => v !== null).sort((a, b) => a - b);
  if (withData.length === 0) return null;
  const mid = Math.floor(withData.length / 2);
  return withData.length % 2 === 0 ? (withData[mid - 1] + withData[mid]) / 2 : withData[mid];
}

// MultiplierRow plus the three trend metrics above, computed once per
// (rows, highThreshold) change rather than recomputed inline in the sort
// comparator and every cell render -- see the `augmentedRows` useMemo
// below. Extends MultiplierRow rather than replacing it so every existing
// function that takes a MultiplierRow (multiplierForWeek, getSortValue)
// keeps working unchanged.
interface AugmentedMultiplierRow extends MultiplierRow {
  highWeeksCount: number;
  highWeeksTotal: number;
  streak: number;
  medianMult: number | null;
  // Same three metrics, computed off the non-TD Multiplier sequence
  // instead -- feeds the Breakout Watch panel (see its own section below).
  nonTdHighWeeksCount: number;
  nonTdHighWeeksTotal: number;
  nonTdStreak: number;
  nonTdMedianMult: number | null;
}

function getSortValue(row: AugmentedMultiplierRow, field: SortField): string | number | null {
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
    case "highWeeksCount":
      return row.highWeeksCount;
    case "streak":
      return row.streak;
    case "medianMult":
      return row.medianMult;
    case "non_td_multiplier":
      return row.non_td_multiplier;
    case "nonTdHighWeeksCount":
      return row.nonTdHighWeeksCount;
    case "nonTdStreak":
      return row.nonTdStreak;
    case "nonTdMedianMult":
      return row.nonTdMedianMult;
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

// Same expand/collapse header pattern as OwnershipSummaryView.tsx's and
// ContestResultsView.tsx's own (duplicated, not shared) CollapsibleHeader --
// the whole header (not just an icon) is the click target, reusing those
// views' own .ownership-summary-collapsible-header/.ownership-summary-
// collapse-icon CSS rather than inventing a second, visually-identical
// style just because this is a different tab. `title` is a ReactNode (not
// just a string, unlike those two) so the "(2+ high weeks...)" hint span
// can sit inside it.
function CollapsibleHeader({ title, expanded, onToggle }: { title: ReactNode; expanded: boolean; onToggle: () => void }) {
  return (
    <div
      className="player-pool-grid-header ownership-summary-collapsible-header"
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      onClick={onToggle}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle();
        }
      }}
    >
      <h3>
        {title}
        <span className="ownership-summary-collapse-icon">{expanded ? "▴" : "▾"}</span>
      </h3>
    </div>
  );
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

  // The "high" bar for the High Weeks/Streak trend columns and the Repeat
  // Performers panel below -- defaults to 4.0 (the top tier only), matching
  // "high week" = "4.0+ Multiplier week". The field is there to loosen that
  // bar, not tighten it: lower it (e.g. to 3.5 or 3.0) to pull more players
  // into High Weeks/Streak/Repeat Performers than the strict 4.0+ default
  // would show. Purely a client-side recompute (see augmentedRows below),
  // not a fetch param, so it's debounced the same way but never triggers a
  // network request.
  const [highThresholdInput, setHighThresholdInput] = useState("4.0");
  const [highThreshold, setHighThreshold] = useState(4.0);
  const highThresholdDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Starts expanded -- the panel's whole point is to be seen first, above
  // the main grid (see where it's rendered below).
  const [repeatPerformersExpanded, setRepeatPerformersExpanded] = useState(true);
  const [breakoutWatchExpanded, setBreakoutWatchExpanded] = useState(true);

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
    const trailingTimer = trailingDebounce;
    const thresholdTimer = highThresholdDebounce;
    return () => {
      if (trailingTimer.current) clearTimeout(trailingTimer.current);
      if (thresholdTimer.current) clearTimeout(thresholdTimer.current);
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

  function commitHighThreshold(value: string) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed >= 0) {
      setHighThreshold(parsed);
    } else {
      setHighThresholdInput(String(highThreshold));
    }
  }

  function handleHighThresholdChange(value: string) {
    setHighThresholdInput(value);
    if (highThresholdDebounce.current) clearTimeout(highThresholdDebounce.current);
    highThresholdDebounce.current = setTimeout(() => {
      highThresholdDebounce.current = null;
      commitHighThreshold(value);
    }, TRAILING_WEEKS_DEBOUNCE_MS);
  }

  function handleHighThresholdBlur() {
    if (highThresholdDebounce.current) {
      clearTimeout(highThresholdDebounce.current);
      highThresholdDebounce.current = null;
    }
    commitHighThreshold(highThresholdInput);
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

  // rows + the three trend metrics, recomputed only when the fetched rows
  // or the High Threshold change -- everything downstream (filtering,
  // sorting, both tables) reads from this instead of `rows` directly.
  const augmentedRows: AugmentedMultiplierRow[] = useMemo(() => {
    const isHighMultiplier = (value: number) => value >= highThreshold;
    return (rows ?? []).map((row) => {
      const sequence = multiplierSequence(row);
      const { count, total } = highWeeksCount(sequence, isHighMultiplier);
      const nonTdSequence = nonTdMultiplierSequence(row);
      // A week only counts as "high" for Breakout Watch if it's in the
      // 2.5-4.0 non-TD-multiplier band AND that same week's own TD FPTS
      // was exactly 0 -- a touchdown in ANY shown week (base or trailing)
      // disqualifies just that week, not the player, per the person's own
      // "if player TD the base or trailing week then that week doesn't
      // count" rule. The week still counts toward the total (see
      // highWeeksCount's own docstring) -- only whether it's "high" changes.
      const tdSequence = tdFptsSequence(row);
      const isBreakoutWatchHighWeek = (value: number, index: number) =>
        inBreakoutWatchBand(value) && tdSequence[index] === 0;
      const nonTd = highWeeksCount(nonTdSequence, isBreakoutWatchHighWeek);
      return {
        ...row,
        highWeeksCount: count,
        highWeeksTotal: total,
        streak: currentStreak(sequence, isHighMultiplier),
        medianMult: medianOf(sequence),
        nonTdHighWeeksCount: nonTd.count,
        nonTdHighWeeksTotal: nonTd.total,
        nonTdStreak: currentStreak(nonTdSequence, isBreakoutWatchHighWeek),
        nonTdMedianMult: medianOf(nonTdSequence),
      };
    });
  }, [rows, highThreshold]);

  // Built from the full unfiltered row set, same "independent filters"
  // convention as every other tab's chip rows.
  const teamOptions = useMemo(() => {
    const teams = new Set<string>();
    for (const row of rows ?? []) teams.add(row.team);
    return [...teams].sort();
  }, [rows]);

  const filteredRows = useMemo(() => {
    const selectedGameTeams = selectedGame ? (gameByKey.get(selectedGame)?.teams ?? []) : null;
    return augmentedRows.filter((row) => {
      if (selectedGameTeams && !selectedGameTeams.includes(row.team)) return false;
      if (selectedPositions.size > 0 && !selectedPositions.has(row.position)) return false;
      if (selectedTeams.size > 0 && !selectedTeams.has(row.team)) return false;
      if (selectedTiers.size > 0) {
        const tier = tierLabel(row.multiplier);
        if (tier === null || !selectedTiers.has(tier)) return false;
      }
      return true;
    });
  }, [augmentedRows, selectedGame, selectedPositions, selectedTeams, selectedTiers, gameByKey]);

  const sortedRows = useMemo(() => {
    return [...filteredRows].sort((a, b) =>
      compareValues(getSortValue(a, sortField), getSortValue(b, sortField), sortDirection)
    );
  }, [filteredRows, sortField, sortDirection]);

  // Repeat Performers -- players who've had at least 2 high weeks within
  // the current window (1 high week isn't "repeated", it's just a good
  // week), scoped to whatever the main grid's own Game/Position/Team/Tier
  // filters currently show rather than the full unfiltered row set, same
  // "filters apply tab-wide" convention as everywhere else here. Sorted by
  // High Weeks count first (the clearest "how often" signal), ties broken
  // by the current streak, then by the overall average -- not reusing the
  // main grid's own sortField/sortDirection, since this panel's whole point
  // is a fixed "who repeats most" ranking rather than something the person
  // re-sorts by column.
  const repeatPerformers = useMemo(() => {
    return filteredRows
      .filter((row) => row.highWeeksCount >= REPEAT_PERFORMER_MIN_HIGH_WEEKS)
      .sort(
        (a, b) => b.highWeeksCount - a.highWeeksCount || b.streak - a.streak || (b.medianMult ?? 0) - (a.medianMult ?? 0)
      );
  }, [filteredRows]);

  // Breakout Watch -- the inverse read of Repeat Performers: players whose
  // NON-TD Multiplier (volume-driven value, TD variance stripped out) has
  // been consistently high (3+ of the shown weeks, see
  // BREAKOUT_WATCH_MIN_HIGH_WEEKS) while their base week's own TD_FPTS is
  // exactly 0 -- real underlying production that hasn't paid off with a
  // touchdown yet, so the total Multiplier still looks pedestrian even
  // though the role says a breakout is coming. Same filtered-rows scoping
  // and tie-break order (count, then streak, then median) as Repeat
  // Performers, just on the non-TD metrics.
  const breakoutCandidates = useMemo(() => {
    return filteredRows
      .filter((row) => row.nonTdHighWeeksCount >= BREAKOUT_WATCH_MIN_HIGH_WEEKS && row.td_fpts === 0)
      .sort(
        (a, b) =>
          b.nonTdHighWeeksCount - a.nonTdHighWeeksCount ||
          b.nonTdStreak - a.nonTdStreak ||
          (b.nonTdMedianMult ?? 0) - (a.nonTdMedianMult ?? 0)
      );
  }, [filteredRows]);

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
          "Multiplier coloring: dark green 4.0+, light green 3.5-3.99, dark gold 3.0-3.49, light gold 2.0-2.99, no color below 2.0 -- applied to every Multiplier/W* column, plus the Median Mult column below.",
          `High Weeks/Streak/Median Mult summarize a player's Multiplier trend across the base week + shown trailing weeks: High Weeks is how many of those weeks were at or above the "High threshold" field (e.g. "4/6"); Streak is the most recent unbroken run of high weeks (0 if the base week itself isn't high, even if earlier weeks were); Median Mult is the middle value across every week with data -- median rather than average so one huge fluke week doesn't drag the number up and hide an otherwise inconsistent player. High threshold defaults to 4.0 (a "high" week means a 4.0+ Multiplier) -- lower it, next to "Weeks to show", to include more players than just the strict 4.0+ crowd.`,
          `Non-TD Mult / Non-TD High Weeks / Non-TD Streak / Median Non-TD Mult are the same style of trend metrics as Multiplier/High Weeks/Streak/Median Mult, but computed against Non-TD FPTS instead of total FPTS -- a player's TD-variance-stripped value trend, since a raw Multiplier can already look "high" off one touchdown alone. Unlike the raw-Multiplier metrics, "high" here is a fixed ${BREAKOUT_WATCH_NON_TD_MULT_MIN}-${BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE} band, not tied to the adjustable "High threshold" field below -- a player already averaging 4.0+ isn't a breakout candidate, they've already broken out.`,
          `Breakout Watch (above the main grid, click the heading to collapse it) lists everyone with ${BREAKOUT_WATCH_MIN_HIGH_WEEKS}+ "high" weeks (within the current "Weeks to show" window) -- a week counts as high only when it's a ${BREAKOUT_WATCH_NON_TD_MULT_MIN}-${BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE} Non-TD Multiplier AND that same week's own TD FPTS was exactly 0; a touchdown in ANY shown week (base or trailing) knocks just that week out of the count, it still shows in Non-TD High Weeks' total (e.g. "1/3") but no longer counts toward the numerator or a streak -- real volume-driven production that hasn't paid off with a touchdown, sorted by Non-TD High Weeks count, then Non-TD Streak, then Median Non-TD Mult (Median is unaffected by the TD rule -- it still reflects every week with data).`,
          "Repeat Performers (above the main grid, click the heading to collapse it) lists everyone with 2+ high weeks within the current filters -- a quick fade-candidate watchlist for players whose price has likely caught up to their recent production, sorted by High Weeks count, then Streak, then Median Mult.",
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
        <label className="game-logs-lookback-field">
          High threshold
          <input
            type="number"
            min={0}
            step={0.1}
            value={highThresholdInput}
            onChange={(e) => handleHighThresholdChange(e.target.value)}
            onBlur={handleHighThresholdBlur}
          />
        </label>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && <p className="hint">{error}</p>}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && rows !== null && (
        <div className="multipliers-repeat-performers">
          <CollapsibleHeader
            title={
              <>
                Breakout Watch{" "}
                <span className="hint">
                  ({BREAKOUT_WATCH_MIN_HIGH_WEEKS}+ weeks with a {BREAKOUT_WATCH_NON_TD_MULT_MIN}-
                  {BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE} non-TD multiplier and 0 TD FPTS that same week --
                  potential buy candidates)
                </span>
              </>
            }
            expanded={breakoutWatchExpanded}
            onToggle={() => setBreakoutWatchExpanded((e) => !e)}
          />
          {breakoutWatchExpanded &&
            (breakoutCandidates.length === 0 ? (
              <p className="hint">
                No players currently on {BREAKOUT_WATCH_MIN_HIGH_WEEKS}+ weeks with a {BREAKOUT_WATCH_NON_TD_MULT_MIN}
                -{BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE} non-TD multiplier and 0 TD FPTS that same week, within
                the current filters and "Weeks to show" window.
              </p>
            ) : (
              <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
                <table className="player-pool-grid ownership-summary-grid multipliers-grid">
                  <thead>
                    <tr>
                      <th className="player-pool-grid-sticky player-selection-name-col">Name</th>
                      <th>Position</th>
                      <th>Team</th>
                      <th>
                        Non-TD
                        <br />
                        High Weeks
                      </th>
                      <th>
                        Non-TD
                        <br />
                        Streak
                      </th>
                      <th>
                        Median
                        <br />
                        Non-TD Mult
                      </th>
                      {multiplierWeekNumbers.map((w) => (
                        <th key={`non-td-mult-w-${w}`}>
                          Non-TD Mult
                          <br />W{w}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {breakoutCandidates.map((row) => (
                      <tr key={`${row.name}-${row.position}`}>
                        <td className="player-pool-grid-sticky player-selection-name-col">{row.name}</td>
                        <td>{row.position}</td>
                        <td>{row.team}</td>
                        <td className="player-pool-grid-num">
                          {row.nonTdHighWeeksCount}/{row.nonTdHighWeeksTotal}
                        </td>
                        <td className="player-pool-grid-num">{row.nonTdStreak}</td>
                        <td className={`player-pool-grid-num ${tierClassName(multiplierTier(row.nonTdMedianMult)) ?? ""}`}>
                          {formatMultiplier(row.nonTdMedianMult)}
                        </td>
                        {multiplierWeekNumbers.map((w) => {
                          const value = nonTdMultiplierForWeek(row, w);
                          return (
                            <td
                              key={`non-td-mult-w-${w}`}
                              className={`player-pool-grid-num ${tierClassName(multiplierTier(value)) ?? ""}`}
                            >
                              {formatMultiplier(value)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
        </div>
      )}

      {!loading && !error && rows !== null && (
        <div className="multipliers-repeat-performers">
          <CollapsibleHeader
            title={
              <>
                Repeat Performers <span className="hint">(2+ high weeks -- potential fade candidates)</span>
              </>
            }
            expanded={repeatPerformersExpanded}
            onToggle={() => setRepeatPerformersExpanded((e) => !e)}
          />
          {repeatPerformersExpanded &&
            (repeatPerformers.length === 0 ? (
              <p className="hint">
                No players currently on {REPEAT_PERFORMER_MIN_HIGH_WEEKS}+ high weeks ({">"}={highThreshold}) within
                the current filters and window.
              </p>
            ) : (
              <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
                <table className="player-pool-grid ownership-summary-grid multipliers-grid">
                  <thead>
                    <tr>
                      <th className="player-pool-grid-sticky player-selection-name-col">Name</th>
                      <th>Position</th>
                      <th>Team</th>
                      <th>High Weeks</th>
                      <th>Streak</th>
                      <th>Median Mult</th>
                      {multiplierWeekNumbers.map((w) => (
                        <th key={`mult-w-${w}`}>
                          Multiplier
                          <br />W{w}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {repeatPerformers.map((row) => (
                      <tr key={`${row.name}-${row.position}`}>
                        <td className="player-pool-grid-sticky player-selection-name-col">{row.name}</td>
                        <td>{row.position}</td>
                        <td>{row.team}</td>
                        <td className="player-pool-grid-num">
                          {row.highWeeksCount}/{row.highWeeksTotal}
                        </td>
                        <td className="player-pool-grid-num">{row.streak}</td>
                        <td className={`player-pool-grid-num ${tierClassName(multiplierTier(row.medianMult)) ?? ""}`}>
                          {formatMultiplier(row.medianMult)}
                        </td>
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
            ))}
        </div>
      )}

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
                <SortableTh
                  field="non_td_multiplier"
                  label={
                    <>
                      Non-TD
                      <br />
                      Mult
                    </>
                  }
                  ariaLabel="Non-TD Multiplier"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="highWeeksCount"
                  label={
                    <>
                      High
                      <br />
                      Weeks
                    </>
                  }
                  ariaLabel="High Weeks"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh field="streak" label="Streak" currentField={sortField} direction={sortDirection} onToggle={toggleSort} />
                <SortableTh
                  field="medianMult"
                  label={
                    <>
                      Median
                      <br />
                      Mult
                    </>
                  }
                  ariaLabel="Median Multiplier"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="nonTdHighWeeksCount"
                  label={
                    <>
                      Non-TD
                      <br />
                      High Weeks
                    </>
                  }
                  ariaLabel="Non-TD High Weeks"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="nonTdStreak"
                  label={
                    <>
                      Non-TD
                      <br />
                      Streak
                    </>
                  }
                  ariaLabel="Non-TD Streak"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
                <SortableTh
                  field="nonTdMedianMult"
                  label={
                    <>
                      Median
                      <br />
                      Non-TD Mult
                    </>
                  }
                  ariaLabel="Median Non-TD Multiplier"
                  currentField={sortField}
                  direction={sortDirection}
                  onToggle={toggleSort}
                />
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
                  <td className={`player-pool-grid-num ${tierClassName(multiplierTier(row.non_td_multiplier)) ?? ""}`}>
                    {formatMultiplier(row.non_td_multiplier)}
                  </td>
                  <td className="player-pool-grid-num">
                    {row.highWeeksTotal > 0 ? `${row.highWeeksCount}/${row.highWeeksTotal}` : "-"}
                  </td>
                  <td className="player-pool-grid-num">{row.streak}</td>
                  <td className={`player-pool-grid-num ${tierClassName(multiplierTier(row.medianMult)) ?? ""}`}>
                    {formatMultiplier(row.medianMult)}
                  </td>
                  <td className="player-pool-grid-num">
                    {row.nonTdHighWeeksTotal > 0 ? `${row.nonTdHighWeeksCount}/${row.nonTdHighWeeksTotal}` : "-"}
                  </td>
                  <td className="player-pool-grid-num">{row.nonTdStreak}</td>
                  <td className={`player-pool-grid-num ${tierClassName(multiplierTier(row.nonTdMedianMult)) ?? ""}`}>
                    {formatMultiplier(row.nonTdMedianMult)}
                  </td>
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
