// Small Week/Opp/Score/Recap table rendered between a team's own <h2>
// header and its stats grid on both Game Logs and Game Logs Against (see
// each view's own usage) -- one row per week that team appears in the
// current lookback window. Shared by both tabs since both group rows by a
// team abbreviation and already carry week/game_location per row (see
// gameLogsShared.ts's distinctTeamWeeks/TeamWeekEntry).
import { formatOpponent } from "./gameLogsShared";
import type { TeamWeekEntry } from "./gameLogsShared";
import type { GameRecapEntry, GameRecapWeekSnapshot } from "../types";
import { findTeamRecap } from "../types";

interface TeamRecapTableProps {
  team: string;
  weeks: TeamWeekEntry[];
  // Keyed by week -- undefined means "haven't tried to fetch this week
  // yet," null means "fetched, nothing scraped for that week."
  recapsByWeek: Map<number, GameRecapWeekSnapshot | null | undefined>;
  onOpenRecap: (entry: GameRecapEntry, sourceUrl: string) => void;
}

export function TeamRecapTable({ team, weeks, recapsByWeek, onOpenRecap }: TeamRecapTableProps) {
  if (weeks.length === 0) return null;

  return (
    <table className="team-recap-table">
      <thead>
        <tr>
          <th scope="col">Week</th>
          <th scope="col">Opp</th>
          <th scope="col">Score</th>
          <th scope="col">Recap</th>
        </tr>
      </thead>
      <tbody>
        {weeks.map((w) => {
          const snapshot = recapsByWeek.get(w.week) ?? null;
          const entry = findTeamRecap(snapshot, team);
          // Game Logs Against's own rows carry no `opponent` field at all
          // (see TeamWeekEntry's own docstring) -- derive it from the
          // recap entry itself (whichever side isn't `team`) when the row
          // didn't already supply one.
          const opponent =
            w.opponent ?? (entry ? (entry.away_team === team ? entry.home_team : entry.away_team) : null);
          const score = entry ? (entry.away_team === team ? entry.away_team_score : entry.home_team_score) : null;
          const oppScore = entry
            ? entry.away_team === team
              ? entry.home_team_score
              : entry.away_team_score
            : null;
          // Win/loss/tie background on the Score cell -- green for a win,
          // red for a loss, white (no class, falls back to the table's
          // default background) for a tie. Only applied when both scores
          // are known; a week with no recap scraped yet shows the plain
          // "-" placeholder with no color.
          const scoreClass =
            score !== null && oppScore !== null
              ? score > oppScore
                ? "team-recap-score-win"
                : score < oppScore
                  ? "team-recap-score-loss"
                  : "team-recap-score-tie"
              : undefined;
          return (
            <tr key={w.week}>
              <td>Week {w.week}</td>
              <td>{formatOpponent(opponent, w.game_location)}</td>
              <td className={scoreClass}>{score !== null && oppScore !== null ? `${score}-${oppScore}` : "-"}</td>
              <td>
                {entry && snapshot ? (
                  <button
                    type="button"
                    className="team-recap-view-link"
                    onClick={() => onOpenRecap(entry, snapshot.source_url)}
                  >
                    View
                  </button>
                ) : (
                  <span className="hint">—</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
