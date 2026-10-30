import { formatSalary } from "./gameLogsShared";
import { useState } from "react";
import type { RbAllowedTdGame, RbRushingAllowedGame, RbRushingGame, RbRushingSummary, RbTdGame } from "../types";
import { CountChip, venue } from "./QbPassingPanel";

// Slate-wide RB rushing-yards panel for the Game Logs Summary tab, modeled on
// QbPassingPanel: two summary lines that are always visible, then an
// expandable table of this week's RBs with their own 100+ and 75-99 games
// and the games their opponent's defense has allowed. Built from
// backend/services/game_logs_summary/rb_rushing.py. Unlike the QB panel, the
// defense columns COMBINE a team's running backs: each line is one game's
// combined total, with every back's own yards listed beside it.

interface RbRushingPanelProps {
  data: RbRushingSummary;
}

function RbGameLines({ games }: { games: RbRushingGame[] }) {
  return (
    <>
      <CountChip count={games.length} />
      {games.map((g) => (
        <div className="qb-passing-line" key={g.week}>
          Week {g.week}: {venue(g.is_home)}
          {g.opponent} {g.rush_yds}
        </div>
      ))}
    </>
  );
}

// "Braelon Allen" -> "B. Allen". Shortens each back so the Opp D cells stay
// narrow; a single-word name is left as is.
export function initialAndLastName(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return name;
  return `${parts[0][0]}. ${parts.slice(1).join(" ")}`;
}

// The week/total stays on one line; the per-back yards sit on an indented
// line beneath it that is allowed to wrap (see .qb-passing-rushers), which is
// what keeps the last two columns from forcing a sideways scroll.
function AllowedLines({ games }: { games: RbRushingAllowedGame[] }) {
  return (
    <>
      <CountChip count={games.length} />
      {games.map((a) => (
        <div key={a.week}>
          <div className="qb-passing-line">
            Week {a.week}: {venue(a.defense_is_home)}
            {a.team} {a.total_yds}
          </div>
          <div className="qb-passing-rushers">
            {a.rushers.map((r) => `${initialAndLastName(r.name)} ${r.rush_yds}`).join(", ")}
          </div>
        </div>
      ))}
    </>
  );
}

// A RB's own 1+ TD games (rushing here, receiving in RbReceivingPanel).
export function RbTdLines({ games }: { games: RbTdGame[] }) {
  return (
    <>
      <CountChip count={games.length} color="green" />
      {games.map((g) => (
        <div className="qb-passing-line" key={g.week}>
          Week {g.week}: {venue(g.is_home)}
          {g.opponent} {g.td} TD
        </div>
      ))}
    </>
  );
}

// Games a defense allowed 1+ TD to a team's RBs combined; scorers wrap
// beneath, same layout as AllowedLines.
export function AllowedTdLines({ games }: { games: RbAllowedTdGame[] }) {
  return (
    <>
      <CountChip count={games.length} color="green" />
      {games.map((a) => (
        <div key={a.week}>
          <div className="qb-passing-line">
            Week {a.week}: {venue(a.defense_is_home)}
            {a.team} {a.total_td} TD
          </div>
          <div className="qb-passing-rushers">
            {a.scorers.map((s) => `${initialAndLastName(s.name)} ${s.td}`).join(", ")}
          </div>
        </div>
      ))}
    </>
  );
}

export function RbRushingPanel({ data }: RbRushingPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const weeks = data.first_week === data.through_week ? `Week ${data.first_week}` : `Weeks ${data.first_week}-${data.through_week}`;
  return (
    <section className="qb-passing-panel">
      <h3>RB rushing yards</h3>
      <p className="qb-passing-summary">
        <strong>{weeks}, main slate:</strong> RBs have {data.rb_games_100} games of 100+ rushing yards and{" "}
        {data.rb_games_75_99} of 75-99. Defenses have allowed {data.defense_allowed_100} games of 100+ and{" "}
        {data.defense_allowed_75_99} of 75-99 to a team's RBs combined. RBs have {data.rb_games_td} games with a rushing TD
        and defenses have allowed {data.defense_allowed_td} to a team's RBs combined.
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
        {expanded ? "Hide" : "Show"} RB table ({data.rows.length} RB{data.rows.length === 1 ? "" : "s"})
      </button>
      {expanded && (
        <>
          <div className="qb-passing-table-wrap">
            <table className="qb-passing-table">
              <thead>
                <tr>
                  <th>RB</th>
                  <th>75+</th>
                  <th>100+</th>
                  <th>75-99</th>
                  <th>Rush TD</th>
                  <th>Opp</th>
                  <th>Opp D allowed 75+</th>
                  <th>Opp D allowed 100+</th>
                  <th>Opp D allowed 75-99</th>
                  <th>Opp D allowed rush TD</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={`${row.name}-${row.team}`}>
                    <td>
                      {row.name} <span className="qb-passing-team">{row.team}</span>
{row.salary !== null && <span className="qb-passing-team"> {formatSalary(row.salary)}</span>}
                      {row.status && <span className="qb-passing-status"> {row.status}</span>}
                    </td>
                    <td>
                      <CountChip count={row.over_100.length + row.range_75_99.length} color="green" />
                    </td>
                    <td>
                      <RbGameLines games={row.over_100} />
                    </td>
                    <td>
                      <RbGameLines games={row.range_75_99} />
                    </td>
                    <td>
                      <RbTdLines games={row.td_games} />
                    </td>
                    <td>{row.opponent}</td>
                    <td>
                      <CountChip count={row.opponent_allowed.length} color="green" />
                    </td>
                    <td>
                      <AllowedLines games={row.opponent_allowed.filter((a) => a.total_yds >= 100)} />
                    </td>
                    <td>
                      <AllowedLines games={row.opponent_allowed.filter((a) => a.total_yds < 100)} />
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
            vs means the team listed was at home, @ means away. A RB appears if he has a 75+ game of his own. The Opp D columns
            add up all of a team's RBs in a game; the names and yards in parentheses are each back's own rushing yards. 75+ is the
            100+ and 75-99 counts added together. The TD columns count games with 1+ rushing TD (the allowed side adds up all
            of a team's RBs, with each scorer's TDs listed beneath); TDs don't add RBs to the table.
          </p>
        </>
      )}
    </section>
  );
}
