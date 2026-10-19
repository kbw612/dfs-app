import { useState } from "react";
import type { RbReceivingAllowedGame, RbReceivingGame, RbReceivingSummary } from "../types";
import { CountChip, venue } from "./QbPassingPanel";
import { AllowedTdLines, RbTdLines, initialAndLastName } from "./RbRushingPanel";

// Slate-wide RB receiving panel for the Game Logs Summary tab, modeled on
// RbRushingPanel: always-visible summary lines, then an expandable table of
// this week's RBs with their own 50+ receiving-yard games and 1+ receiving-TD
// games, beside the same games their opponent's defense has allowed (RBs
// combined; each back's own number listed). Built from
// backend/services/game_logs_summary/rb_receiving.py.

interface RbReceivingPanelProps {
  data: RbReceivingSummary;
}

function RbGameLines({ games }: { games: RbReceivingGame[] }) {
  return (
    <>
      <CountChip count={games.length} color="green" />
      {games.map((g) => (
        <div className="qb-passing-line" key={g.week}>
          Week {g.week}: {venue(g.is_home)}
          {g.opponent} {g.rec_yds}
        </div>
      ))}
    </>
  );
}

function AllowedLines({ games }: { games: RbReceivingAllowedGame[] }) {
  return (
    <>
      <CountChip count={games.length} color="green" />
      {games.map((a) => (
        <div key={a.week}>
          <div className="qb-passing-line">
            Week {a.week}: {venue(a.defense_is_home)}
            {a.team} {a.total_yds}
          </div>
          <div className="qb-passing-rushers">
            {a.receivers.map((r) => `${initialAndLastName(r.name)} ${r.rec_yds}`).join(", ")}
          </div>
        </div>
      ))}
    </>
  );
}

export function RbReceivingPanel({ data }: RbReceivingPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const weeks = data.first_week === data.through_week ? `Week ${data.first_week}` : `Weeks ${data.first_week}-${data.through_week}`;
  return (
    <section className="qb-passing-panel">
      <h3>RB receiving</h3>
      <p className="qb-passing-summary">
        <strong>{weeks}, main slate:</strong> RBs have {data.rb_games_50} games of 50+ receiving yards and defenses have
        allowed {data.defense_allowed_50} to a team's RBs combined. RBs have {data.rb_games_td} games with a receiving TD and
        defenses have allowed {data.defense_allowed_td} to a team's RBs combined.
      </p>
      {data.best_setups.length > 0 && (
        <p className="qb-passing-summary">
          <strong>Best setups:</strong>{" "}
          {data.best_setups.map((s) => `${s.name} vs ${s.opponent} (${s.allowed_count} allowed)`).join(", ")}
        </p>
      )}
      <button
        type="button"
        className="qb-passing-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Hide" : "Show"} RB receiving table ({data.rows.length} RB{data.rows.length === 1 ? "" : "s"})
      </button>
      {expanded && (
        <>
          <div className="qb-passing-table-wrap">
            <table className="qb-passing-table">
              <thead>
                <tr>
                  <th>RB</th>
                  <th>50+ rec yds</th>
                  <th>Rec TD</th>
                  <th>Opp</th>
                  <th>Opp D allowed 50+ rec yds</th>
                  <th>Opp D allowed rec TD</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={`${row.name}-${row.team}`}>
                    <td>
                      {row.name} <span className="qb-passing-team">{row.team}</span>
                      {row.status && <span className="qb-passing-status"> {row.status}</span>}
                    </td>
                    <td>
                      <RbGameLines games={row.games_50} />
                    </td>
                    <td>
                      <RbTdLines games={row.td_games} />
                    </td>
                    <td>{row.opponent}</td>
                    <td>
                      <AllowedLines games={row.opponent_allowed} />
                    </td>
                    <td>
                      <AllowedTdLines games={row.opponent_allowed_td} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            vs means the team listed was at home, @ means away. A RB appears if he has a 50+ receiving-yard game of his own. The
            Opp D columns add up all of a team's RBs in a game (names and numbers beneath are each back's own); the TD columns
            count games with 1+ receiving TD and don't add RBs to the table.
          </p>
        </>
      )}
    </section>
  );
}
