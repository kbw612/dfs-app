import { formatSalary } from "./gameLogsShared";
import { useState } from "react";
import type { QbAllowedTdGame, QbPassingAllowedGame, QbPassingGame, QbPassingSummary, QbTdGame } from "../types";

// Slate-wide QB passing-yards panel for the Game Logs Summary tab -- two
// summary lines that are always visible, then an expandable table of this
// week's QBs with their own 300+ and 265-299 games and the 265+ games their
// opponent's defense has allowed. Built from backend/services/
// game_logs_summary/qb_passing.py.

interface QbPassingPanelProps {
  data: QbPassingSummary;
}

// "vs" = that team was at home, "@" = away; blank when the Schedule file
// couldn't say.
export function venue(isHome: boolean | null): string {
  if (isHome === null) return "";
  return isHome ? "vs " : "@ ";
}

// Green chip for a non-zero count; a muted plain 0 otherwise so an empty
// bucket doesn't read as a hit.
// Green is the combined 265+ total; blue is a single 300+ or 265-299 bucket.
export function CountChip({ count, color = "blue" }: { count: number; color?: "green" | "blue" }) {
  return count === 0 ? (
    <div className="qb-passing-count zero">0</div>
  ) : (
    <span className={`qb-passing-badge${color === "blue" ? " blue" : ""}`}>{count}</span>
  );
}

// One defense's allowed games (already filtered to a single yardage bucket).
function AllowedLines({ games }: { games: QbPassingAllowedGame[] }) {
  return (
    <>
      <CountChip count={games.length} />
      {games.map((a) => (
        <div className="qb-passing-line" key={`${a.week}-${a.passer}`}>
          Week {a.week}: {a.passer} {venue(a.defense_is_home)}
          {a.passer_team} {a.pass_yds}
        </div>
      ))}
    </>
  );
}

// A defense's 3+ passing-TD games, same line format as the yardage lists.
function AllowedTdLines({ games }: { games: QbAllowedTdGame[] }) {
  return (
    <>
      <CountChip count={games.length} color="green" />
      {games.map((a) => (
        <div className="qb-passing-line" key={`${a.week}-${a.passer}`}>
          Week {a.week}: {a.passer} {venue(a.defense_is_home)}
          {a.passer_team} {a.pass_td} TD
        </div>
      ))}
    </>
  );
}

function QbTdLines({ games }: { games: QbTdGame[] }) {
  return (
    <>
      <CountChip count={games.length} color="green" />
      {games.map((g) => (
        <div className="qb-passing-line" key={g.week}>
          Week {g.week}: {venue(g.is_home)}
          {g.opponent} {g.pass_td} TD
        </div>
      ))}
    </>
  );
}

function QbGameLines({ games }: { games: QbPassingGame[] }) {
  return (
    <>
      <CountChip count={games.length} />
      {games.map((g) => (
        <div className="qb-passing-line" key={g.week}>
          Week {g.week}: {venue(g.is_home)}
          {g.opponent} {g.pass_yds}
        </div>
      ))}
    </>
  );
}

export function QbPassingPanel({ data }: QbPassingPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const weeks = data.first_week === data.through_week ? `Week ${data.first_week}` : `Weeks ${data.first_week}-${data.through_week}`;
  return (
    <section className="qb-passing-panel">
      <h3>QB passing yards</h3>
      <p className="qb-passing-summary">
        <strong>{weeks}, main slate:</strong> QBs have {data.qb_games_300} games of 300+ passing yards and{" "}
        {data.qb_games_265_299} of 265-299. Defenses have allowed {data.defense_allowed_300} of 300+ and{" "}
        {data.defense_allowed_265_299} of 265-299. QBs have {data.qb_games_td3} games of 3+ passing TDs and defenses have
        allowed {data.defense_allowed_td3}.
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
        {expanded ? "Hide" : "Show"} QB table ({data.rows.length} QB{data.rows.length === 1 ? "" : "s"})
      </button>
      {expanded && (
      <>
      <div className="qb-passing-table-wrap">
        <table className="qb-passing-table">
          <thead>
            <tr>
              <th>QB</th>
              <th>265+</th>
              <th>300+</th>
              <th>265-299</th>
              <th>3+ pass TD</th>
              <th>Opp</th>
              <th>Opp D allowed 265+</th>
              <th>Opp D allowed 300+</th>
              <th>Opp D allowed 265-299</th>
              <th>Opp D allowed 3+ pass TD</th>
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
                  <CountChip count={row.over_300.length + row.range_265_299.length} color="green" />
                </td>
                <td>
                  <QbGameLines games={row.over_300} />
                </td>
                <td>
                  <QbGameLines games={row.range_265_299} />
                </td>
                <td>
                  <QbTdLines games={row.td_games} />
                </td>
                <td>{row.opponent}</td>
                <td>
                  <CountChip count={row.opponent_allowed.length} color="green" />
                </td>
                <td>
                  <AllowedLines games={row.opponent_allowed.filter((a) => a.pass_yds >= 300)} />
                </td>
                <td>
                  <AllowedLines games={row.opponent_allowed.filter((a) => a.pass_yds < 300)} />
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
        vs means the team listed was at home, @ means away. 265+ is the 300+ and 265-299 counts added together; the 300+ and 265-299 columns never overlap.
        The TD columns count games with 3+ passing TDs. A QB appears with a 265+ or 3+ TD game of his own, or as his team's
        primary QB facing a defense that allowed either. Backup QBs appear only when they have such a game themselves.
      </p>
      </>
      )}
    </section>
  );
}
