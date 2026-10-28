import { Fragment, useState } from "react";
import type { FptsCell, PositionFptsSummary } from "../types";
import { CountChip } from "./QbPassingPanel";

// FPTS panel for one position (QB, RB, WR, TE or DST). Display only: the
// backend sends the counts, the preformatted game lines and the group sizes
// (backend/services/game_logs_summary/position_fpts.py).

function Cell({ cell, color }: { cell: FptsCell; color: "blue" | "green" }) {
  return (
    <>
      <CountChip count={cell.count} color={color} />
      {cell.lines.map((line) => (
        <div className="qb-passing-line" key={line.text}>
          {line.text}
          {line.details.map((detail) => (
            <span className="fpts-detail" key={detail}>
              {detail}
            </span>
          ))}
        </div>
      ))}
    </>
  );
}

export function PositionFptsPanel({ data }: { data: PositionFptsSummary }) {
  const pos = data.position;
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="qb-passing-panel">
      <h3>{pos} FPTS</h3>
      <p className="qb-passing-summary">
        <strong>{data.weeks_label}, main slate:</strong> {pos}s have {data.player_games_elite} Elite ({data.elite_label}) and{" "}
        {data.player_games_strong} Strong ({data.strong_label}) FPTS games. {data.opponent_label === "Opp offense" ? "Offenses" : "Defenses"} have
        allowed {data.allowed_elite} Elite and {data.allowed_strong} Strong.
      </p>
      {data.best_setups.length > 0 && (
        <p className="qb-passing-summary">
          <strong>Best setups:</strong> {data.best_setups.join(", ")}
        </p>
      )}
      <button
        type="button"
        className="qb-passing-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Hide" : "Show"} {pos} FPTS table ({data.row_count} {pos}
        {data.row_count === 1 ? "" : "s"})
      </button>
      {expanded && (
        <>
          <div className="qb-passing-table-wrap">
            <table className="qb-passing-table">
              <thead>
                <tr>
                  <th>{pos}</th>
                  <th>Elite {data.elite_label}</th>
                  <th>Strong {data.strong_label}</th>
                  <th>Opp</th>
                  <th>
                    {data.opponent_label} allowed {data.elite_label}
                  </th>
                  <th>
                    {data.opponent_label} allowed {data.strong_label}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.groups.map((group) => (
                  <Fragment key={group.opponent}>
                    <tr className="qb-passing-group-row">
                      <td colSpan={6}>
                        vs {group.opponent} {data.opponent_label === "Opp offense" ? "offense" : "defense"}{" "}
                        <span className="qb-passing-team">
                          {group.allowed_elite.count} allowed {data.elite_label} · {group.allowed_strong.count} allowed {data.strong_label}
                        </span>
                      </td>
                    </tr>
                    {group.rows.map((row, i) => (
                      <tr key={`${row.name}-${row.team}`}>
                        <td>
                          {row.name} <span className="qb-passing-team">{row.team}</span>
                          {row.status && <span className="qb-passing-status"> {row.status}</span>}
                        </td>
                        <td className="fpts-elite">
                          <Cell cell={row.elite} color="green" />
                        </td>
                        <td className="fpts-strong">
                          <Cell cell={row.strong} color="green" />
                        </td>
                        {i === 0 && (
                          <>
                            <td rowSpan={group.row_count}>{group.opponent}</td>
                            <td rowSpan={group.row_count} className="fpts-elite">
                              <Cell cell={group.allowed_elite} color="blue" />
                            </td>
                            <td rowSpan={group.row_count} className="fpts-strong">
                              <Cell cell={group.allowed_strong} color="blue" />
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            Elite and Strong are fantasy-point bands for {pos}s ({data.elite_label} and {data.strong_label}). The salary in parentheses is that week's DK
            salary. vs means the team listed was at home, @ means away. Players are grouped by the{" "}
            {data.opponent_label === "Opp offense" ? "offense" : "defense"} they face this week, and that group's allowed games are shown once. A {pos}{" "}
            appears if he has an Elite or Strong game of his own.
          </p>
        </>
      )}
    </section>
  );
}
