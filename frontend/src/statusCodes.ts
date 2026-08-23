// The full set of valid depth-chart player status codes. Used by the
// status filter (multi-select chips) and the status key (collapsible
// code -> meaning legend) in the UI.
//
// `code` is the value actually matched against a change's current status
// (i.e. what the backend/scraper produces) and is what the status key
// lists first. `label`, when set, overrides what the filter chip displays
// -- Q/D/O show their full word instead of the bare letter since those
// are easy to misread as filter chips.
export interface StatusCode {
  code: string;
  label?: string;
  description: string;
}

// Filter chip order, as specified.
export const STATUS_CODES: StatusCode[] = [
  { code: "Q", label: "Questionable", description: "Injured and questionable to play" },
  { code: "D", label: "Doubtful", description: "Injured and doubtful to play" },
  { code: "O", label: "Out", description: "Injured and will not play" },
  { code: "IR", description: "Injured Reserve" },
  { code: "IR-R", description: "Injured Reserve, Eligible to Return" },
  { code: "SUS", description: "Suspended and unable to play" },
  { code: "PUP", description: "Physically Unable to Perform" },
  { code: "NFI", description: "Non-Football Injury List" },
  { code: "CEL", description: "Commissioner Exempt List" },
  { code: "EX", description: "Roster Exemption" },
  { code: "COV", description: "COVID-Related Illness Exempt List" },
];
