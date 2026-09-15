import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { fetchGameLogsAgainst } from "../api";
import type { GameLogAgainstRow, GameOption } from "../types";
import {
  formatMultiplier,
  formatOpponent,
  formatPct,
  formatSalary,
  multiplierTier,
  positionRank,
  tierClassName,
} from "./gameLogsShared";

// season/week/platform come from the shared header control (see App.tsx),
// same as Game Logs. No `contest` -- reads the same always-All-Games DK
// Players tracker Game Logs does.
interface GameLogsAgainstViewProps {
  season: number;
  week: number;
  platform: string;
}

const LOOKBACK_DEBOUNCE_MS = 800;

interface AgainstGroup {
  team: string;
  rows: GameLogAgainstRow[];
}

// Against-team (alphabetical) > Position (QB/RB/WR/TE/DST order) > week
// descending, then FPTS descending within that week -- same layout
// convention as Game Logs' own groupByTeamAndPosition, just grouped by
// `against_team` (the team being evaluated as an opponent) instead of
// the rostered player's own team.
function groupByAgainstTeamAndPosition(rows: GameLogAgainstRow[]): AgainstGroup[] {
  const byTeam = new Map<string, GameLogAgainstRow[]>();
  for (const row of rows) {
    if (!byTeam.has(row.against_team)) byTeam.set(row.against_team, []);
    byTeam.get(row.against_team)!.push(row);
  }
  return [...byTeam.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([team, teamRows]) => ({
      team,
      rows: [...teamRows].sort((a, b) => {
        const posDiff = positionRank(a.position) - positionRank(b.position);
        if (posDiff !== 0) return posDiff;
        if (a.week !== b.week) return b.week - a.week;
        return b.fpts - a.fpts;
      }),
    }));
}

// Week, Name, Pos, Salary, GameLoc, Multiplier, FPTS, Non-TD FPTS,
// Non-TD %, TD FPTS, TD %.
const GAME_LOG_AGAINST_COLUMN_COUNT = 11;

export function GameLogsAgainstView({ season, week, platform }: GameLogsAgainstViewProps) {
  const [lookbackInput, setLookbackInput] = useState("6");
  const [lookbackWeeks, setLookbackWeeks] = useState(6);
  const lookbackDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [games, setGames] = useState<GameOption[]>([]);
  const [rows, setRows] = useState<GameLogAgainstRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Single-select, same Game filter shape as Game Logs -- selecting a
  // game shows both teams' own "Against" panels together (per the
  // "Game filter shows both teams" decision), since each row already
  // carries its own against_team to filter/group on.
  const [selectedGame, setSelectedGame] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchGameLogsAgainst(season, week, platform, lookbackWeeks)
      .then((result) => {
        setRows(result.rows);
        setGames(result.games);
      })
      .catch((err) => {
        setRows(null);
        setGames([]);
        setError(err instanceof Error ? err.message : "Failed to load game logs against");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, lookbackWeeks]);

  useEffect(() => {
    const timer = lookbackDebounce;
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function commitLookback(value: string) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) {
      setLookbackWeeks(Math.floor(parsed));
    } else {
      setLookbackInput(String(lookbackWeeks));
    }
  }

  function handleLookbackChange(value: string) {
    setLookbackInput(value);
    if (lookbackDebounce.current) clearTimeout(lookbackDebounce.current);
    lookbackDebounce.current = setTimeout(() => {
      lookbackDebounce.current = null;
      commitLookback(value);
    }, LOOKBACK_DEBOUNCE_MS);
  }

  function handleLookbackBlur() {
    if (lookbackDebounce.current) {
      clearTimeout(lookbackDebounce.current);
      lookbackDebounce.current = null;
    }
    commitLookback(lookbackInput);
  }

  const gameByKey = useMemo(() => new Map(games.map((g) => [g.key, g])), [games]);

  const filteredRows = useMemo(() => {
    const selectedGameTeams = selectedGame ? (gameByKey.get(selectedGame)?.teams ?? []) : null;
    return (rows ?? []).filter((row) => {
      if (selectedGameTeams && !selectedGameTeams.includes(row.against_team)) return false;
      return true;
    });
  }, [rows, selectedGame, gameByKey]);

  const groups = useMemo(() => groupByAgainstTeamAndPosition(filteredRows), [filteredRows]);

  const isNotFound = error !== null && error.includes("No DK Players tracker started yet");

  return (
    <>
      <p className="hint">
        For each team in this week's slate, how opposing players performed in their own game against that team over
        the last {lookbackWeeks} week
        {lookbackWeeks === 1 ? "" : "s"} -- Salary/FPTS/Multiplier come from the DK Players tracker, GameLoc from the
        Schedule file. Weeks with 0 FPTS are hidden except for DST, which always shows.
      </p>

      <div className="filters">
        <div className="chip-filter">
          <span className="filter-label">Game</span>
          <div className="chip-row">
            <button
              type="button"
              className={`chip${selectedGame === null ? " selected" : ""}`}
              aria-pressed={selectedGame === null}
              onClick={() => setSelectedGame(null)}
            >
              All
            </button>
            {games.map((g) => (
              <button
                key={g.key}
                type="button"
                className={`chip${selectedGame === g.key ? " selected" : ""}`}
                aria-pressed={selectedGame === g.key}
                onClick={() => setSelectedGame((current) => (current === g.key ? null : g.key))}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>
        <label className="game-logs-lookback-field">
          Weeks of history
          <input
            type="number"
            min={1}
            max={17}
            value={lookbackInput}
            onChange={(e) => handleLookbackChange(e.target.value)}
            onBlur={handleLookbackBlur}
          />
        </label>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && <p className="hint">{error}</p>}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && rows !== null && groups.length === 0 && (
        <p className="hint">No game log rows match the current filters.</p>
      )}

      {!loading &&
        !error &&
        groups.map((group) => (
          <section className="ownership-section" key={group.team}>
            <h2>Against {group.team}</h2>
            <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
              <table className="player-pool-grid ownership-summary-grid">
                <tbody>
                  {group.rows.map((row, idx) => {
                    const previous = group.rows[idx - 1];
                    const showPositionHeader = !previous || previous.position !== row.position;
                    return (
                      <Fragment key={`${row.name}-${row.week}`}>
                        {showPositionHeader && previous && (
                          <tr className="game-logs-position-spacer-row">
                            <td colSpan={GAME_LOG_AGAINST_COLUMN_COUNT}></td>
                          </tr>
                        )}
                        {showPositionHeader && (
                          <tr className="game-logs-position-header-row">
                            <th>Week</th>
                            <th className="player-selection-name-col">Name</th>
                            <th>{row.position}</th>
                            <th>Salary</th>
                            <th>GameLoc</th>
                            <th>Multiplier</th>
                            <th>FPTS</th>
                            <th>
                              Non-TD
                              <br />
                              FPTS
                            </th>
                            <th>
                              Non-TD
                              <br />%
                            </th>
                            <th>
                              TD
                              <br />
                              FPTS
                            </th>
                            <th>TD %</th>
                          </tr>
                        )}
                        <tr>
                          <td>{row.week}</td>
                          <td className="player-selection-name-col">{row.name}</td>
                          <td></td>
                          <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
                          <td>{formatOpponent(group.team, row.game_location)}</td>
                          <td className={`player-pool-grid-num ${tierClassName(multiplierTier(row.multiplier)) ?? ""}`}>
                            {formatMultiplier(row.multiplier)}
                          </td>
                          <td className="player-pool-grid-num">{row.fpts.toFixed(1)}</td>
                          <td className="player-pool-grid-num">{row.non_td_fpts.toFixed(1)}</td>
                          <td className="player-pool-grid-num">{formatPct(row.non_td_fpts_pct)}</td>
                          <td className="player-pool-grid-num">{row.td_fpts.toFixed(1)}</td>
                          <td className="player-pool-grid-num">{formatPct(row.td_fpts_pct)}</td>
                        </tr>
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        ))}
    </>
  );
}
