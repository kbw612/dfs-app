// Small formatting/display helpers shared by Game Logs (GameLogsView.tsx)
// and Game Logs Against (GameLogsAgainstView.tsx) -- both tabs render the
// same Salary/Multiplier/FPTS/Non-TD/TD columns over a DK Players tracker
// row, just over a different row set (one team's own roster history vs.
// every opposing player who faced a given team). Pulled out here once a
// second caller needed them, rather than duplicating -- mirrors the
// backend's own scoring.py extraction (backend/services/game_logs/
// scoring.py), per an explicit "share code between the game logs and game
// logs against" request.

// DST shows up in both tabs' roster -- kept last in the position-group
// order since it's the least common case, and it's the only position
// exempt from either tab's "hide 0-FPTS rows" backend-side filter.
export const POSITION_ORDER = ["QB", "RB", "WR", "TE", "DST"] as const;

export function positionRank(position: string): number {
  const idx = POSITION_ORDER.indexOf(position as (typeof POSITION_ORDER)[number]);
  return idx === -1 ? POSITION_ORDER.length : idx;
}

export function formatMultiplier(value: number | null): string {
  return value === null ? "-" : `${value.toFixed(2)}x`;
}

export function formatPct(value: number | null): string {
  return value === null ? "-" : `${value.toFixed(1)}%`;
}

export function formatCount(value: number | null): string {
  return value === null ? "-" : String(value);
}

// For a plain decimal stat that isn't a percentage or a "3.6x"-style
// multiplier -- QB's own passing Avg (yards/attempt) and Rtg (passer
// rating) -- one decimal place, no suffix.
export function formatDecimal(value: number | null): string {
  return value === null ? "-" : value.toFixed(1);
}

export function formatSalary(value: number): string {
  return `$${value.toLocaleString()}`;
}

// Matches the exact 4-band conditional formatting from the user's
// original Google Sheet (screenshotted directly from its Conditional
// format rules panel): >=4 dark green, 3.5-3.99 light green, 3-3.499
// dark gold, 2-2.999 light gold. Below 2 gets no color, same as that
// sheet's own rules (nothing defined under 2).
export type MultiplierTier = "green-dark" | "green-light" | "yellow-dark" | "yellow-light" | null;

export function multiplierTier(value: number | null): MultiplierTier {
  if (value === null) return null;
  if (value >= 4) return "green-dark";
  if (value >= 3.5) return "green-light";
  if (value >= 3) return "yellow-dark";
  if (value >= 2) return "yellow-light";
  return null;
}

export function tierClassName(tier: MultiplierTier): string | undefined {
  return tier ? `game-logs-tier-${tier}` : undefined;
}

// Highlights the top 2 Tgt Share %/Touch Share % values on the SAME team
// in the SAME week -- ranked independently per column (a player's Touch
// Share rank has no bearing on their Tgt Share rank) and independently
// per (team, week) pair, not across the whole visible row set -- a team's
// own leader in Week 3 shouldn't be compared against a different team's
// leader in Week 5. `getTeam` is passed in rather than assumed to be a
// fixed field name since Game Logs' own rows carry the rostered player's
// `team` while Game Logs Against's rows carry `against_team` instead (see
// each view's own caller).
//
// Ties share a rank -- if two players on that team are tied for that
// week's single highest value, both get the dark shade and there is no
// light-shade player that week (rather than arbitrarily picking one as
// "2nd"). Reuses the same two green shades as the Multiplier column's own
// tiering (game-logs-tier-green-dark/-light) rather than inventing new
// colors.
export function rankTopSharesByTeamAndWeek<T extends { week: number }>(
  rows: T[],
  getTeam: (row: T) => string,
  getValue: (row: T) => number | null
): Map<T, 1 | 2> {
  const rowsByTeamWeek = new Map<string, T[]>();
  for (const row of rows) {
    const key = `${getTeam(row)}|${row.week}`;
    if (!rowsByTeamWeek.has(key)) rowsByTeamWeek.set(key, []);
    rowsByTeamWeek.get(key)!.push(row);
  }

  const ranks = new Map<T, 1 | 2>();
  for (const groupRows of rowsByTeamWeek.values()) {
    const distinctValuesDesc = [
      ...new Set(groupRows.map(getValue).filter((value): value is number => value !== null)),
    ].sort((a, b) => b - a);
    const [topValue, secondValue] = distinctValuesDesc;
    for (const row of groupRows) {
      const value = getValue(row);
      if (value === null) continue;
      if (value === topValue) ranks.set(row, 1);
      else if (value === secondValue) ranks.set(row, 2);
    }
  }
  return ranks;
}

export function shareRankClassName(rank: 1 | 2 | undefined): string {
  if (rank === 1) return "game-logs-tier-green-dark";
  if (rank === 2) return "game-logs-tier-green-light";
  return "";
}

// "vs CLE" / "@ CLE" / "BYE" / "-" (opponent or game_location missing --
// no Schedule file uploaded, or no schedule row for this team/week).
// Game Logs Against has no separate `opponent` field on its own row (the
// panel heading already names the opposing team), so this takes the two
// values directly rather than a whole row object -- lets both tabs' own
// row shapes call it without one needing a field the other doesn't have.
export function formatOpponent(opponent: string | null, gameLocation: "Home" | "Away" | "BYE" | null): string {
  if (opponent === null || gameLocation === null) return "-";
  if (gameLocation === "BYE") return "BYE";
  return gameLocation === "Home" ? `vs ${opponent}` : `@ ${opponent}`;
}
