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

// "low"/"high"/null (from the backend's tier_for_stat_value) -> the
// shared darker-red/darker-green CSS classes (.stat-tier-low/-high, see
// App.css) used for Pass Att/Pass Yds/Rush Att/Rush Yds volume shading --
// both in the Team Summary (Avg/Median) section's own StatAverage cells
// (PlayerStatSummaryTable.tsx) and in the per-week grid's own Pass Att/
// Pass Yds cells (GameLogsView.tsx/GameLogsAgainstView.tsx -- rush/rec
// keep their own unrelated rankTopSharesByTeamAndWeek shading there
// instead). All math/thresholds happen server-side; this just maps the
// tier string to a class name.
export function statTierClassName(tier: "low" | "high" | null): string {
  if (tier === "low") return "stat-tier-low";
  if (tier === "high") return "stat-tier-high";
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

// Team display order mirrors Game Previews' own: teams grouped by
// matchup, in the `games` list's own order (already sorted by game
// label -- "AWAY @ HOME" -- server-side, see build_game_options), each
// game's own two teams in that GameOption's own `teams` order (e.g. the
// week's first two games giving ARI, NYG, DAL, HOU rather than a flat
// alphabetical ARI, DAL, HOU, NYG). Game Logs/Game Logs Against cover
// every team with any stat history, not just this week's slate (unlike
// Game Previews), so a team that isn't in any of this week's games (a
// bye, or no Schedule file yet) has no entry here at all -- callers sort
// those teams after every known team, alphabetically among themselves,
// via the Map's own "not found" (undefined) fallback.
export function buildGameTeamOrder(games: { teams: string[] }[]): Map<string, number> {
  const order = new Map<string, number>();
  let index = 0;
  for (const game of games) {
    for (const team of game.teams) {
      if (!order.has(team)) order.set(team, index++);
    }
  }
  return order;
}

// Sorts team groups by their game order first (teams from the same/
// earlier game before teams from a later one), falling back to plain
// alphabetical for any team not in `teamOrder` (see buildGameTeamOrder's
// own docstring) -- and alphabetical as the tie-break even among ordered
// teams, so two teams from the same game never swap order on a re-render.
export function compareTeamsByGameOrder(teamOrder: Map<string, number>): (a: string, b: string) => number {
  return (a, b) => {
    const rankA = teamOrder.get(a);
    const rankB = teamOrder.get(b);
    if (rankA !== undefined && rankB !== undefined && rankA !== rankB) return rankA - rankB;
    if (rankA !== undefined && rankB === undefined) return -1;
    if (rankA === undefined && rankB !== undefined) return 1;
    return a.localeCompare(b);
  };
}

export interface TeamWeekEntry {
  week: number;
  game_location: "Home" | "Away" | "BYE" | null;
  // Game Logs' own rows carry this directly; Game Logs Against's rows
  // don't (see formatOpponent's own comment) -- TeamRecapTable falls back
  // to deriving the opponent from a found GameRecapEntry instead when this
  // is null, so both tabs can share one component.
  opponent: string | null;
}

// One entry per distinct week present in `rows` (newest first), each
// carrying a representative game_location/opponent for that week -- every
// row sharing a (team, week) pair came from the same game, so the first
// row's own values are as good as any other's.
export function distinctTeamWeeks<T extends TeamWeekEntry>(rows: T[]): TeamWeekEntry[] {
  const byWeek = new Map<number, TeamWeekEntry>();
  for (const row of rows) {
    if (!byWeek.has(row.week)) {
      byWeek.set(row.week, { week: row.week, game_location: row.game_location, opponent: row.opponent });
    }
  }
  return [...byWeek.values()].sort((a, b) => b.week - a.week);
}
