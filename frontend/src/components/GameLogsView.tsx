import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { fetchGameLogs } from "../api";
import type { GameLogRow, GameOption } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import {
  formatCount,
  formatMultiplier,
  formatOpponent,
  formatPct,
  formatSalary,
  multiplierTier,
  positionRank,
  tierClassName,
} from "./gameLogsShared";

// season/week/platform come from the shared header control (see App.tsx),
// same as every other weekly tab. No `contest` -- the DK Players tracker
// this reads from is hardcoded to always read the All Games files (see
// DkPlayersView.tsx's own history), so there's nothing contest-scoped to
// pass through here.
interface GameLogsViewProps {
  season: number;
  week: number;
  platform: string;
}

// How long to wait after the last keystroke in the "Weeks of history"
// input before refetching -- same idea as Settings' Salary Multiplier
// debounce, just refetching instead of saving.
const LOOKBACK_DEBOUNCE_MS = 800;

interface TeamGroup {
  team: string;
  rows: GameLogRow[];
}

// Team (alphabetical) > Position (QB/RB/WR/TE order) > week descending,
// then FPTS descending within that week -- the "Group by position,
// interleaved by week" layout the user picked, matching the reference
// Google Sheet's own per-position blocks with multiple players'
// rows interleaved by week, with each week's own rows led by whoever
// scored the most that week.
function groupByTeamAndPosition(rows: GameLogRow[]): TeamGroup[] {
  const byTeam = new Map<string, GameLogRow[]>();
  for (const row of rows) {
    if (!byTeam.has(row.team)) byTeam.set(row.team, []);
    byTeam.get(row.team)!.push(row);
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

// Week, Name, Pos, Salary, Opp, Multiplier, FPTS, Non-TD FPTS, Non-TD %,
// TD FPTS, TD %, Touches, Tgts, Rec, Rec Yds, Rush Att, Rush Yds.
const GAME_LOG_COLUMN_COUNT = 17;

export function GameLogsView({ season, week, platform }: GameLogsViewProps) {
  const [lookbackInput, setLookbackInput] = useState("6");
  const [lookbackWeeks, setLookbackWeeks] = useState(6);
  const lookbackDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [games, setGames] = useState<GameOption[]>([]);
  const [rows, setRows] = useState<GameLogRow[] | null>(null);
  const [referenceWeek, setReferenceWeek] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Single-select -- only one game at a time, per the user's explicit
  // "I only want to select one game at a time" answer. null = "All".
  const [selectedGame, setSelectedGame] = useState<string | null>(null);
  // Multi-select, independent of the Game filter above -- same
  // ChipMultiSelect used everywhere else in the app (Usage Bump Players,
  // Ownership Summary's Position filter).
  const [selectedTeams, setSelectedTeams] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchGameLogs(season, week, platform, lookbackWeeks)
      .then((result) => {
        setRows(result.rows);
        setGames(result.games);
        setReferenceWeek(result.reference_week);
      })
      .catch((err) => {
        setRows(null);
        setGames([]);
        setReferenceWeek(null);
        setError(err instanceof Error ? err.message : "Failed to load game logs");
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

  // Deliberately built from the full unfiltered row set, not narrowed by
  // whichever Game is currently selected -- same "independent filters"
  // convention as every other tab's chip rows (e.g. Ownership Summary's
  // Position filter doesn't narrow based on other filters either).
  const teamOptions = useMemo(() => {
    const teams = new Set<string>();
    for (const row of rows ?? []) teams.add(row.team);
    return [...teams].sort();
  }, [rows]);

  const filteredRows = useMemo(() => {
    const selectedGameTeams = selectedGame ? (gameByKey.get(selectedGame)?.teams ?? []) : null;
    return (rows ?? []).filter((row) => {
      if (selectedGameTeams && !selectedGameTeams.includes(row.team)) return false;
      if (selectedTeams.size > 0 && !selectedTeams.has(row.team)) return false;
      return true;
    });
  }, [rows, selectedGame, selectedTeams, gameByKey]);

  const groups = useMemo(() => groupByTeamAndPosition(filteredRows), [filteredRows]);

  const isNotFound = error !== null && error.includes("No DK Players tracker started yet");

  return (
    <>
      <p className="hint">
        Each currently-rostered QB/RB/WR/TE/DST's own history from the last {lookbackWeeks} week
        {lookbackWeeks === 1 ? "" : "s"}
        {referenceWeek !== null ? ` (roster as of week ${referenceWeek})` : ""} -- Salary/FPTS/Multiplier come from
        the DK Players tracker, Opponent/GameLoc from the Schedule file, and Touch/Tgts/Rec/etc. from the FantasyData
        weekly stats files. Any of those come back "-" until the relevant Settings upload exists. Weeks with 0 FPTS
        are hidden except for DST, which always shows.
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
        <ChipMultiSelect label="Team" options={teamOptions} selected={selectedTeams} onChange={setSelectedTeams} />
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
            <h2>{group.team}</h2>
            <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
              <table className="player-pool-grid ownership-summary-grid">
                <tbody>
                  {group.rows.map((row, idx) => {
                    const previous = group.rows[idx - 1];
                    const showPositionHeader = !previous || previous.position !== row.position;
                    return (
                      <Fragment key={`${row.name}-${row.week}`}>
                        {showPositionHeader && previous && (
                          // Blank spacer row between one position group's
                          // last row and the next group's own header --
                          // only between groups, not before the very
                          // first one at the top of the table.
                          <tr className="game-logs-position-spacer-row">
                            <td colSpan={GAME_LOG_COLUMN_COUNT}></td>
                          </tr>
                        )}
                        {showPositionHeader && (
                          // Repeats the full column header before every
                          // position group, instead of one header for the
                          // whole table -- the Pos column doubles as the
                          // group's own label (e.g. "QB") here, which is
                          // also why each data row below leaves that
                          // column blank rather than repeating it.
                          <tr className="game-logs-position-header-row">
                            <th>Week</th>
                            <th className="player-selection-name-col">Name</th>
                            <th>{row.position}</th>
                            <th>Salary</th>
                            <th>Opp</th>
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
                            <th>Touches</th>
                            <th>Tgts</th>
                            <th>Rec</th>
                            <th>Rec Yds</th>
                            <th>
                              Rush
                              <br />
                              Att
                            </th>
                            <th>
                              Rush
                              <br />
                              Yds
                            </th>
                          </tr>
                        )}
                        <tr>
                          <td>{row.week}</td>
                          <td className="player-selection-name-col">{row.name}</td>
                          <td></td>
                          <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
                          <td>{formatOpponent(row.opponent, row.game_location)}</td>
                          <td className={`player-pool-grid-num ${tierClassName(multiplierTier(row.multiplier)) ?? ""}`}>
                            {formatMultiplier(row.multiplier)}
                          </td>
                          <td className="player-pool-grid-num">{row.fpts.toFixed(1)}</td>
                          <td className="player-pool-grid-num">{row.non_td_fpts.toFixed(1)}</td>
                          <td className="player-pool-grid-num">{formatPct(row.non_td_fpts_pct)}</td>
                          <td className="player-pool-grid-num">{row.td_fpts.toFixed(1)}</td>
                          <td className="player-pool-grid-num">{formatPct(row.td_fpts_pct)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.touches)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.targets)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.receptions)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.receiving_yards)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.rush_att)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.rush_yards)}</td>
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
