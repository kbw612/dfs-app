// The full set of valid depth-chart player status codes, and what each
// one means -- used by the status key (StatusKey.tsx) to explain every
// individual code, regardless of how they're grouped for filtering below.
export interface StatusCode {
  code: string;
  label?: string;
  description: string;
}

// Status key order, as specified.
export const STATUS_CODES: StatusCode[] = [
  { code: "Q", label: "Questionable", description: "Injured and questionable to play" },
  { code: "D", label: "Doubtful", description: "Injured and doubtful to play" },
  { code: "O", description: "Out" },
  { code: "IR", description: "Injured Reserve" },
  { code: "IR-R", description: "Injured Reserve, Eligible to Return" },
  { code: "SUS", description: "Suspended and unable to play" },
  { code: "PUP", description: "Physically Unable to Perform" },
  { code: "NFI", description: "Non-Football Injury List" },
  { code: "CEL", description: "Commissioner Exempt List" },
  { code: "EX", description: "Roster Exemption" },
  { code: "COV", description: "COVID-Related Illness Exempt List" },
];

// Filter chip groups -- what StatusFilter (and any other status-filter UI)
// actually renders and toggles. Q and D each stay their own chip (still
// eligible to play, just banged up); every other code effectively means
// "not going to play this week," so they collapse into one "Out" chip --
// filtering for every unavailable player shouldn't require checking 9
// separate boxes. `key` is the identity stored in a filter's
// `selected: Set<string>`; `codes` is every raw status code that chip
// matches.
export interface StatusFilterGroup {
  key: string;
  label: string;
  codes: string[];
}

export const STATUS_FILTER_GROUPS: StatusFilterGroup[] = [
  { key: "Q", label: "Questionable", codes: ["Q"] },
  { key: "D", label: "Doubtful", codes: ["D"] },
  { key: "O", label: "Out", codes: ["O", "IR", "IR-R", "SUS", "PUP", "NFI", "CEL", "EX", "COV"] },
];

// Subset of the "O" group's own codes that typically mean the player is
// out for multiple weeks (a real injury-reserve/suspension/exemption
// designation), rather than just this single week's game-day "Out" (O) or
// a short, day-to-day COVID exemption (COV) -- these get a visibly darker
// red than plain "O" so a glance at the shade tells you "gone a while" vs
// "just this week." Kept as its own list (not derived from STATUS_CODES)
// since the multi-week distinction is a display-only judgment call, not a
// property inherent to the code itself.
const MULTI_WEEK_OUT_CODES = ["IR", "IR-R", "SUS", "PUP", "NFI", "CEL", "EX"];

export function isMultiWeekOut(status: string): boolean {
  return MULTI_WEEK_OUT_CODES.includes(status);
}

// Shared match logic for every status-filter consumer (DiffResults.tsx,
// DepthChartsView.tsx) -- true if `status` falls under any currently
// selected filter group. An empty `selected` set means "no filter active,"
// which callers handle themselves before ever reaching here (matches the
// pre-existing convention: empty selection shows everything, not nothing).
export function statusMatchesFilter(status: string | null, selected: Set<string>): boolean {
  if (status === null) return false;
  for (const group of STATUS_FILTER_GROUPS) {
    if (selected.has(group.key) && group.codes.includes(status)) return true;
  }
  return false;
}

// Font-color rule for a player's current status, used by DepthChartsView.tsx:
// "Out" and Doubtful both mean the player's role this week is seriously in
// doubt or gone entirely, so both get red; Questionable is a lighter
// warning, so it gets gold instead. Within the "Out" group, a multi-week
// code (IR, SUS, PUP, etc. -- see isMultiWeekOut) gets a darker red than
// plain "O" or Doubtful, since those mean gone for a while rather than
// just this week. No color (undefined) for a healthy player (status null)
// -- reuses the "O" group's own codes list as the single source of truth
// for what counts as "Out," rather than duplicating that list a third time.
export function statusColorClassName(status: string | null): string | undefined {
  if (status === null) return undefined;
  if (status === "Q") return "status-color-gold";
  const outCodes = STATUS_FILTER_GROUPS.find((g) => g.key === "O")!.codes;
  if (isMultiWeekOut(status)) return "status-color-red-dark";
  if (status === "D" || outCodes.includes(status)) return "status-color-red";
  return undefined;
}

// Background-shading counterpart to statusColorClassName -- same rule the
// Injury Report tab uses to shade a whole row (see InjuryReportView.tsx's
// injuryStatusRowClassName / .injury-report-row-out/-out-multi-week/
// -questionable), reused here for DepthChartsView.tsx where there's no
// whole row to shade (several players sit inline in one position's own
// <li>), just the one player's own name. "Out" and Doubtful shade red
// regardless of star status; a multi-week Out code shades a darker red
// (see isMultiWeekOut). Questionable is different, matching Injury Report
// exactly: the yellow only shows up for a STARRED Questionable player -- a
// non-starred Questionable player gets no background at all. Undefined
// for a healthy player (status null).
export function statusBackgroundClassName(status: string | null, starred: boolean): string | undefined {
  if (status === null) return undefined;
  if (status === "Q") return starred ? "status-bg-questionable" : undefined;
  const outCodes = STATUS_FILTER_GROUPS.find((g) => g.key === "O")!.codes;
  if (isMultiWeekOut(status)) return "status-bg-out-multi-week";
  if (status === "D" || outCodes.includes(status)) return "status-bg-out";
  return undefined;
}
