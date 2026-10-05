// Avg/Median TEAM summary rendered between TeamRecapTable (the Week/Opp/
// Score/Recap outcomes table) and the main per-week stats grid on both
// Game Logs and Game Logs Against (see each view's own usage) -- one row
// (there's only ever one, for the team/panel this section is already
// under) averaging/medianing Rec TD/Rush Att/Rush Yds/Rush TD/Pass Att/
// Pass Yds/Pass TD over exactly the weeks already shown below it --
// every currently-shown player's own value is summed into a team-week
// total first, THEN averaged/medianed across weeks (a team total, not a
// per-player one -- see TeamStatSummaryRow's own docstring in types.ts).
// Rec/Rec Yds were dropped from this section at the person's own
// request. All math, including the background-color tiers on Pass Att/
// Pass Yds/Rush Att/Rush Yds, happens server-side (backend/services/
// game_logs/game_logs_engine.py's build_team_stat_summary/
// tier_for_stat_value) -- this component only renders the numbers (and
// tiers) it's given, per an explicit "no calcs on the frontend" request.
import { Fragment } from "react";
import type { StatAverage, TeamStatSummaryRow } from "../types";
import { statTierClassName } from "./gameLogsShared";
import { HeaderInfoPopover } from "./HeaderInfoPopover";
import { statTierNotes } from "./scoringNotes";

interface PlayerStatSummaryTableProps {
  // Expected to be 0 or 1 entries -- the caller filters the full
  // team_stat_summary list down to just this section's own team before
  // passing it in (there's one TeamStatSummaryRow per team league-wide).
  rows: TeamStatSummaryRow[];
}

type StatKey = "rec_td" | "rush_att" | "rush_yards" | "rush_td" | "pass_att" | "pass_yds" | "pass_td";

// Same Rush/Pass block order the main stats grid itself uses for these
// same columns. `thresholds` (low, high), where present, is this stat's
// own red/green tier cutoffs (see tier_for_stat_value) -- shown via the
// column header's own info icon; the 3 TD stats have no thresholds at
// all (never shaded), so they get no icon.
const STAT_COLUMNS: { key: StatKey; label: string; thresholds?: [number, number] }[] = [
  { key: "rec_td", label: "Rec TD" },
  { key: "rush_att", label: "Rush Att", thresholds: [21, 30] },
  { key: "rush_yards", label: "Rush Yds", thresholds: [85, 141] },
  { key: "rush_td", label: "Rush TD" },
  { key: "pass_att", label: "Pass Att", thresholds: [28, 38] },
  { key: "pass_yds", label: "Pass Yds", thresholds: [175, 261] },
  { key: "pass_td", label: "Pass TD" },
];

function formatStat(value: number | null): string {
  return value === null ? "-" : value.toFixed(1);
}

export function PlayerStatSummaryTable({ rows }: PlayerStatSummaryTableProps) {
  if (rows.length === 0) return null;

  return (
    <div className="player-pool-grid-wrap ownership-summary-grid-wrap player-stat-summary-wrap">
      <span className="player-stat-summary-label">Team Summary (Avg / Median)</span>
      <table className="player-pool-grid ownership-summary-grid player-stat-summary-table">
        <thead>
          <tr>
            <th rowSpan={2}>Games</th>
            {STAT_COLUMNS.map((col) => (
              <th key={col.key} colSpan={2}>
                {col.label}
                {col.thresholds && (
                  <HeaderInfoPopover title={col.label} lines={statTierNotes(col.thresholds[0], col.thresholds[1])} />
                )}
              </th>
            ))}
          </tr>
          <tr>
            {STAT_COLUMNS.map((col) => (
              <Fragment key={col.key}>
                <th>Avg</th>
                <th>Median</th>
              </Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.team}>
              <td className="player-pool-grid-num">{row.games}</td>
              {STAT_COLUMNS.map((col) => {
                const stat: StatAverage = row[col.key];
                return (
                  <Fragment key={col.key}>
                    <td className={`player-pool-grid-num ${statTierClassName(stat.average_tier)}`}>
                      {formatStat(stat.average)}
                    </td>
                    <td className={`player-pool-grid-num ${statTierClassName(stat.median_tier)}`}>
                      {formatStat(stat.median)}
                    </td>
                  </Fragment>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
