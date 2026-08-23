// Preset position-group filters for the diff results view. Grouped into
// broad categories first (Fantasy/Offensive/Defensive/Special Teams --
// these overlap on purpose, e.g. QB belongs to both Fantasy and
// Offensive) followed by individual position-type breakdowns. "Kickers"
// uses PK, not K -- PK (place-kicker) is the only kicker code this app's
// data actually has (see DESIRED_POSITION_ORDER in scraper.py).

export interface PositionFilter {
  label: string;
  positions: string[];
}

export const POSITION_FILTER_GROUPS: PositionFilter[] = [
  { label: "Fantasy", positions: ["QB", "RB", "FB", "WR", "TE", "PK"] },
  { label: "Offensive", positions: ["QB", "RB", "FB", "WR", "TE", "LT", "LG", "C", "RG", "RT"] },
  {
    label: "Defensive",
    positions: [
      "LDE", "LDT", "NT", "RDE", "RDT",
      "LILB", "MLB", "WLB", "SLB", "RILB",
      "LCB", "RCB", "SCB", "FS", "SS",
    ],
  },
  { label: "Special Teams", positions: ["PK", "KR", "PR", "P", "H", "LS"] },
];

export const POSITION_FILTER_INDIVIDUAL: PositionFilter[] = [
  { label: "Quarterbacks", positions: ["QB"] },
  { label: "Running Backs", positions: ["RB", "FB"] },
  { label: "Wide Receivers", positions: ["WR"] },
  { label: "Tight Ends", positions: ["TE"] },
  { label: "Kickers", positions: ["PK"] },
  { label: "Offensive Line", positions: ["LT", "LG", "C", "RG", "RT"] },
  { label: "Defensive Line", positions: ["LDE", "LDT", "NT", "RDE", "RDT"] },
  { label: "Linebackers", positions: ["LILB", "MLB", "WLB", "SLB", "RILB"] },
  { label: "Defensive Backs", positions: ["LCB", "RCB", "SCB", "FS", "SS"] },
];

export const POSITION_FILTERS: PositionFilter[] = [
  ...POSITION_FILTER_GROUPS,
  ...POSITION_FILTER_INDIVIDUAL,
];

// The Usage Bump Players page restricts its position filter to skill
// positions only -- "opportunity" is a fantasy-relevant concept there, and
// offensive line/defense/special teams bumps aren't useful for that
// page's purpose. Deliberately narrower than any of the presets above
// ("Fantasy" also includes PK; "Running Backs" also includes FB).
export const OFFENSIVE_FANTASY_POSITIONS: string[] = ["QB", "RB", "WR", "TE"];

export function positionsForFilter(label: string): Set<string> | null {
  const found = POSITION_FILTERS.find((f) => f.label === label);
  return found ? new Set(found.positions) : null;
}

// Union of positionsForFilter() across several selected preset labels --
// used by the Usage Bump Players page, whose position filter is
// multi-select (unlike the single-select one on the Compare page).
export function positionsForFilters(labels: Iterable<string>): Set<string> {
  const result = new Set<string>();
  for (const label of labels) {
    const positions = positionsForFilter(label);
    if (positions) {
      for (const position of positions) result.add(position);
    }
  }
  return result;
}
