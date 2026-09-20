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
// doubt or gone entirely, so both get the same red; Questionable is a
// lighter warning, so it gets gold instead. No color (undefined) for a
// healthy player (status null) -- reuses the "O" group's own codes list
// as the single source of truth for what counts as "Out," rather than
// duplicating that list a third time.
export function statusColorClassName(status: string | null): string | undefined {
  if (status === null) return undefined;
  if (status === "Q") return "status-color-gold";
  const outCodes = STATUS_FILTER_GROUPS.find((g) => g.key === "O")!.codes;
  if (status === "D" || outCodes.includes(status)) return "status-color-red";
  return undefined;
}
