// Position Depth filter for the Compare tab -- distinct from the Usage
// Bump Players tab's own Position Depth filter (UsageBumpView.tsx),
// which has a fixed 1-4 option list and no escape hatch. This one is
// fully data-driven once a comparison has run: some position groups run
// deeper than others (a WR6 is unremarkable, a QB6 basically never
// happens), so the chip list is built from whatever depths actually show
// up in the current diff -- not a fixed 1-4 floor.
//
// - Before any comparison has run (diff === null), chips 1-13 are shown
//   as placeholders, all unselected -- there's nothing to filter yet
//   (DiffResults shows "No comparison run yet." regardless of chip
//   state), so nothing starts checked (see defaultDepthFilter).
// - Once a comparison *has* run, that whole 1-13 placeholder range is
//   dropped and replaced with whichever depths actually appear in the
//   diff's results, in ascending order -- could be fewer chips, more, or
//   go past 13, depending on the data.
// - Selection auto-updates every time a *new* comparison loads (see
//   autoDepthFilter), discarding whatever the user had manually picked
//   for the previous comparison: chips 1 through the deepest depth
//   actually present get selected, capped at 4 (deeper chips like 5+
//   always start unselected, even if that comparison reaches depth 8) --
//   the range always starts at 1 regardless of whether every depth in
//   between literally appears (e.g. only depth-3 changes still selects
//   1-3). The user can still freely toggle chips after that; it's only
//   the *next* comparison that recomputes and overwrites the selection.
// - A trailing NO_DEPTH_OPTION chip covers changes with no current depth
//   at all -- team-level changes (defensive_formation, field set instead
//   of player/rank) and removed players (current === null). Always
//   present (not data-driven); auto-selected whenever the comparison has
//   at least one such row.
//
// Unlike the Status/Position filters on this page, an empty selection
// here does NOT mean "no filter, show everything" -- it means "show
// nothing." This filter is always active.

import type { Change, DiffResult } from "./types";
import { isPlayerChangeValue } from "./types";

export const NO_DEPTH_OPTION = "N/A";

// Shown before any comparison has run, purely so the filter row has its
// eventual shape from the start -- replaced entirely by the diff's actual
// depths as soon as one loads.
const PLACEHOLDER_DEPTHS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"];

// Auto-select is always capped here -- depths past this never get picked
// automatically, only 1-through-this-cap does (see autoDepthFilter).
const AUTO_SELECT_CAP = 4;

interface DiffDepths {
  maxDepth: number; // 0 if no player-level changes at all
  hasNoDepth: boolean; // any team-level change or removed player
}

function analyzeDiffDepths(diff: DiffResult): DiffDepths {
  let maxDepth = 0;
  let hasNoDepth = false;
  for (const c of diff.changes) {
    if (isPlayerChangeValue(c.current)) {
      maxDepth = Math.max(maxDepth, c.current.rank);
    } else {
      hasNoDepth = true;
    }
  }
  return { maxDepth, hasNoDepth };
}

export function depthFilterOptions(diff: DiffResult | null): string[] {
  if (!diff) {
    return [...PLACEHOLDER_DEPTHS, NO_DEPTH_OPTION];
  }
  const depths = new Set<number>();
  for (const c of diff.changes) {
    if (isPlayerChangeValue(c.current)) {
      depths.add(c.current.rank);
    }
  }
  const sorted = [...depths].sort((a, b) => a - b).map(String);
  return [...sorted, NO_DEPTH_OPTION];
}

// The starting selection before any comparison has run -- nothing checked,
// since there's nothing to filter yet.
export function defaultDepthFilter(): Set<string> {
  return new Set();
}

// The selection to switch to every time a *new* comparison loads: 1
// through the deepest depth actually present (capped at AUTO_SELECT_CAP),
// plus NO_DEPTH_OPTION if the comparison has any team-level changes or
// removed players. Call this after every successful comparison fetch --
// it replaces whatever was selected before, per rule.
export function autoDepthFilter(diff: DiffResult): Set<string> {
  const { maxDepth, hasNoDepth } = analyzeDiffDepths(diff);
  const cap = Math.min(maxDepth, AUTO_SELECT_CAP);
  const selected = new Set<string>();
  for (let depth = 1; depth <= cap; depth++) {
    selected.add(String(depth));
  }
  if (hasNoDepth) {
    selected.add(NO_DEPTH_OPTION);
  }
  return selected;
}

// Matches a change's *current* depth against the selected chips -- same
// "current, not previous" convention as the Status filter (a player who
// moved from depth 2 to depth 5 only matches if 5 is selected).
export function matchesDepth(c: Change, selected: Set<string>): boolean {
  if (isPlayerChangeValue(c.current)) {
    return selected.has(String(c.current.rank));
  }
  return selected.has(NO_DEPTH_OPTION);
}
