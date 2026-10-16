import { useState } from "react";
import type { QbPassingAllowedGame, QbPassingGame, QbPassingSummary } from "../types";

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
function venue(isHome: boolean | null): string {
  if (isHome === null) return "";
  return isHome ? "vs " : "@ ";
}

// Green chip for a non-zero count; a muted plain 0 otherwise so an empty
// bucket doesn't read as a hit.
function CountChip({ count }: { count: number }) {
  return count === 0 ? <div className="qb-passing-count zero">0</div> : <span className="qb-passing-badge">{count}</span>;
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
        {data.defense_allowed_265_299} of 265-299.
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
              <th>300+</th>
              <th>265-299</th>
              <th>Opp</th>
              <th>Opp D allowed 300+</th>
              <th>Opp D allowed 265-299</th>
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
                  <QbGameLines games={row.over_300} />
                </td>
                <td>
                  <QbGameLines games={row.range_265_299} />
                </td>
                <td>{row.opponent}</td>
                <td>
                  <AllowedLines games={row.opponent_allowed.filter((a) => a.pass_yds >= 300)} />
                </td>
                <td>
                  <AllowedLines games={row.opponent_allowed.filter((a) => a.pass_yds < 300)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        vs means the team listed was at home, @ means away. The 300+ and 265-299 columns never overlap.
        Backup QBs appear only when they have a 265+ game of their own.
      </p>
      </>
      )}
    </section>
  );
}
