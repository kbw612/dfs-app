import { Fragment, useState } from "react";
import type { PositionMultiplierAllowedGame, PositionMultiplierGame, PositionMultiplierSummary } from "../types";
import { CountChip, venue } from "./QbPassingPanel";

// Slate-wide salary-multiplier panel (one each for QB, RB, WR and TE) for the
// Game Logs Summary tab, built from backend/services/game_logs_summary/
// position_multipliers.py: players with 4x+, 3-3.99x or non-TD 2.5x+ games in
// the window, beside the same games each opponent's defense has allowed. Each
// allowed line is one player's game (a
// multiplier belongs to one priced player), not a combined team number.

interface PositionMultiplierPanelProps {
  data: PositionMultiplierSummary;
}

// "4.00x ($6.0K)" -- the multiplier and that week's DK salary.
function fmt(m: number, salary: number): string {
  return `${m.toFixed(2)}x ($${(salary / 1000).toFixed(1)}K)`;
}

function OwnLines({ games, color }: { games: PositionMultiplierGame[]; color: "blue" | "green" }) {
  return (
    <>
      <CountChip count={games.length} color={color} />
      {games.map((g) => (
        <div className="qb-passing-line" key={g.week}>
          Week {g.week}: {venue(g.is_home)}
          {g.opponent} {fmt(g.multiplier, g.salary)}
        </div>
      ))}
    </>
  );
}

function AllowedLines({ games, color }: { games: PositionMultiplierAllowedGame[]; color: "blue" | "green" }) {
  return (
    <>
      <CountChip count={games.length} color={color} />
      {games.map((a) => (
        <div className="qb-passing-line" key={`${a.week}-${a.player}`}>
          Week {a.week}: {a.player} {venue(a.defense_is_home)}
          {a.player_team} {fmt(a.multiplier, a.salary)}
        </div>
      ))}
    </>
  );
}

export function PositionMultiplierPanel({ data }: PositionMultiplierPanelProps) {
  const pos = data.position;
  const [expanded, setExpanded] = useState(false);
  const weeks = data.first_week === data.through_week ? `Week ${data.first_week}` : `Weeks ${data.first_week}-${data.through_week}`;
  return (
    <section className="qb-passing-panel">
      <h3>{pos} salary multipliers</h3>
      <p className="qb-passing-summary">
        <strong>{weeks}, main slate:</strong> {pos}s have {data.player_games_4x} games of 4x+ and {data.player_games_3x_399} of 3-3.99x,
        and {data.player_games_non_td_2_5x} with a non-TD multiplier of 2.5x+. Defenses have allowed {data.defense_allowed_4x} of 4x+,{" "}
        {data.defense_allowed_3x_399} of 3-3.99x and {data.defense_allowed_non_td_2_5x} non-TD 2.5x+.
      </p>
      {data.best_setups.length > 0 && (
        <p className="qb-passing-summary">
          <strong>Best setups:</strong>{" "}
          {data.best_setups.map((s) => `${s.name} vs ${s.opponent} (${s.allowed_count} allowed 3x+)`).join(", ")}
        </p>
      )}
      <button
        type="button"
        className="qb-passing-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Hide" : "Show"} {pos} multiplier table ({data.rows.length} {pos}{data.rows.length === 1 ? "" : "s"})
      </button>
      {expanded && (
        <>
          <div className="qb-passing-table-wrap">
            <table className="qb-passing-table">
              <thead>
                <tr>
                  <th>{pos}</th>
                  <th>3x+</th>
                  <th>4x+</th>
                  <th>3-3.99x</th>
                  <th>Non-TD 2.5x+</th>
                  <th>Opp</th>
                  <th>Opp D allowed 3x+</th>
                  <th>Opp D allowed 4x+</th>
                  <th>Opp D allowed 3-3.99x</th>
                  <th>Opp D allowed non-TD 2.5x+</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => {
                  const firstInGroup = i === 0 || data.rows[i - 1].opponent !== row.opponent;
                  // How many rows share this defense -- the Opp and Opp D cells are
                  // drawn once and span the group instead of repeating per player.
                  const groupSize = firstInGroup
                    ? data.rows.slice(i).findIndex((other) => other.opponent !== row.opponent)
                    : 0;
                  const span = groupSize === -1 ? data.rows.length - i : groupSize;
                  return (
                  <Fragment key={`${row.name}-${row.team}`}>
                    {/* Group header: rows arrive sorted so each defense's players are
                        contiguous; show the defense once above its group. */}
                    {firstInGroup && (
                      <tr className="qb-passing-group-row">
                        <td colSpan={10}>
                          vs {row.opponent} defense{" "}
                          <span className="qb-passing-team">
                            {row.opponent_allowed.length} allowed 3x+ · {row.opponent_allowed_non_td.length} non-TD 2.5x+
                          </span>
                        </td>
                      </tr>
                    )}
                  <tr>
                    <td>
                      {row.name} <span className="qb-passing-team">{row.team}</span>
                      {row.status && <span className="qb-passing-status"> {row.status}</span>}
                    </td>
                    <td>
                      <CountChip count={row.over_4x.length + row.range_3x_399.length} color="green" />
                    </td>
                    <td>
                      <OwnLines games={row.over_4x} color="blue" />
                    </td>
                    <td>
                      <OwnLines games={row.range_3x_399} color="blue" />
                    </td>
                    <td>
                      <OwnLines games={row.non_td_2_5x} color="green" />
                    </td>
                    {firstInGroup && (
                      <>
                        <td rowSpan={span}>{row.opponent}</td>
                        <td rowSpan={span}>
                          <CountChip count={row.opponent_allowed.length} color="green" />
                        </td>
                        <td rowSpan={span}>
                          <AllowedLines games={row.opponent_allowed.filter((a) => a.multiplier >= 4)} color="blue" />
                        </td>
                        <td rowSpan={span}>
                          <AllowedLines games={row.opponent_allowed.filter((a) => a.multiplier < 4)} color="blue" />
                        </td>
                        <td rowSpan={span}>
                          <AllowedLines games={row.opponent_allowed_non_td} color="green" />
                        </td>
                      </>
                    )}
                  </tr>
                  </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Multiplier is fantasy points per $1,000 of salary; non-TD is the same with touchdown points removed. The salary in parentheses is that week's DK salary. vs means the team
            listed was at home, @ means away. 3x+ is the 4x+ and 3-3.99x counts added together; non-TD 2.5x+ lists only games not already in
            the 3x+ columns. Players are grouped by the defense they face this week, and that defense's Opp D cells are shown once for the whole group. A {pos} appears if he has a 3x+ or non-TD 2.5x+ game of his own. Each Opp D line is one {pos}'s game.
          </p>
        </>
      )}
    </section>
  );
}
