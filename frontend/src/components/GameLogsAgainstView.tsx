import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { fetchGameLogsAgainst } from "../api";
import type { GameLogAgainstRow, GameOption } from "../types";
import { CollapsibleHint } from "./CollapsibleHint";
import {
  formatCount,
  formatDecimal,
  formatMultiplier,
  formatOpponent,
  formatPct,
  formatSalary,
  multiplierTier,
  positionRank,
  rankTopSharesByTeamAndWeek,
  shareRankClassName,
  tierClassName,
} from "./gameLogsShared";

// season/week/platform/contest come from the shared header control (see
// App.tsx), same as Game Logs. Reads the same always-All-Games DK Players
// tracker Game Logs does -- `contest` here only narrows which teams get
// an "Against" panel down to the currently-selected Contest's own DK
// salary slate (see GameLogsView.tsx's own comment, and backend/api/
// game_logs_against/game_logs_against.py's docstring).
interface GameLogsAgainstViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
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
// Non-TD %, TD FPTS, TD %, Opp Share, Tgt Share, Touch Share, Touches,
// Tgts, Rec, Rec Yds, Rec TD, Rush Att, Rush Yds, Rush TD, Pass Cmp, Pass
// Att, Pass Cmp%, Pass Yds, Pass Avg, Pass TD, Pass Int, Pass Sck, Pass
// Rtg. DST's own group adds one extra Sacks column right after TD % (not
// counted here since the spacer row's colSpan just needs to cover at
// least the widest group).
const GAME_LOG_AGAINST_COLUMN_COUNT = 32;

export function GameLogsAgainstView({ season, week, platform, contest }: GameLogsAgainstViewProps) {
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
    fetchGameLogsAgainst(season, week, platform, lookbackWeeks, contest)
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
  }, [season, week, platform, contest, lookbackWeeks]);

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

  // Same top-2-per-team-per-week highlighting as Game Logs' own -- keyed
  // by `against_team` rather than a `team` field (GameLogAgainstRow has no
  // field for the opposing player's own team), which still isolates each
  // (real team, week) pair correctly: within one "Against {team}" panel,
  // every row shown for a given week is already that week's single real
  // opponent's own players (see gameLogsShared.rankTopSharesByTeamAndWeek
  // and this component's own groupByAgainstTeamAndPosition).
  const oppShareRanks = useMemo(
    () => rankTopSharesByTeamAndWeek(filteredRows, (r) => r.against_team, (r) => r.opp_share_pct),
    [filteredRows]
  );
  const targetShareRanks = useMemo(
    () => rankTopSharesByTeamAndWeek(filteredRows, (r) => r.against_team, (r) => r.target_share_pct),
    [filteredRows]
  );
  const touchShareRanks = useMemo(
    () => rankTopSharesByTeamAndWeek(filteredRows, (r) => r.against_team, (r) => r.touch_share_pct),
    [filteredRows]
  );

  const isNotFound = error !== null && error.includes("No DK Players tracker started yet");

  return (
    <>
      <CollapsibleHint
        items={[
          `For each team in this week's slate, how opposing players performed in their own game against that team
          over the last ${lookbackWeeks} week${lookbackWeeks === 1 ? "" : "s"}.`,
          "Salary/FPTS/Multiplier come from the DK Players tracker; GameLoc comes from the Schedule file.",
          `Touch/Tgts/Rec/Rec Yds/Rec TD/Rush Att/Rush Yds/Rush TD/Opp Share/Tgt Share/Touch Share/Pass stats come from the
          FantasyData weekly stats files (same definitions as Game Logs' own), computed once when "Calc Week
          Points & Fantasy Data" is run for that week.`,
          "Tgt Share is targets divided by the team's combined pass attempts.",
          "Touch Share is (carries + receptions) divided by (team carries + team receptions).",
          "Opp Share is (carries + targets) divided by (team carries + team targets).",
          "The 9 Pass columns are QB-only.",
          "Weeks with 0 FPTS are hidden except for DST, which always shows.",
        ]}
      />

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
                            {row.position === "DST" && <th>Sacks</th>}
                            <th>
                              Opp
                              <br />
                              Share
                            </th>
                            <th>
                              Tgt
                              <br />
                              Share
                            </th>
                            <th>
                              Touch
                              <br />
                              Share
                            </th>
                            <th>Touches</th>
                            <th>Tgts</th>
                            <th>Rec</th>
                            <th>Rec Yds</th>
                            <th>
                              Rec
                              <br />
                              TD
                            </th>
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
                            <th>
                              Rush
                              <br />
                              TD
                            </th>
                            <th>
                              Pass
                              <br />
                              Cmp
                            </th>
                            <th>
                              Pass
                              <br />
                              Att
                            </th>
                            <th>
                              Pass
                              <br />
                              Cmp%
                            </th>
                            <th>
                              Pass
                              <br />
                              Yds
                            </th>
                            <th>
                              Pass
                              <br />
                              Avg
                            </th>
                            <th>
                              Pass
                              <br />
                              TD
                            </th>
                            <th>
                              Pass
                              <br />
                              Int
                            </th>
                            <th>
                              Pass
                              <br />
                              Sck
                            </th>
                            <th>
                              Pass
                              <br />
                              Rtg
                            </th>
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
                          {row.position === "DST" && (
                            <td className="player-pool-grid-num">{formatCount(row.sacks)}</td>
                          )}
                          <td className={`player-pool-grid-num ${shareRankClassName(oppShareRanks.get(row))}`}>
                            {formatPct(row.opp_share_pct)}
                          </td>
                          <td className={`player-pool-grid-num ${shareRankClassName(targetShareRanks.get(row))}`}>
                            {formatPct(row.target_share_pct)}
                          </td>
                          <td className={`player-pool-grid-num ${shareRankClassName(touchShareRanks.get(row))}`}>
                            {formatPct(row.touch_share_pct)}
                          </td>
                          <td className="player-pool-grid-num">{formatCount(row.touches)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.targets)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.receptions)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.receiving_yards)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.rec_td)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.rush_att)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.rush_yards)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.rush_td)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.pass_cmp)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.pass_att)}</td>
                          <td className="player-pool-grid-num">{formatPct(row.pass_cmp_pct)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.pass_yds)}</td>
                          <td className="player-pool-grid-num">{formatDecimal(row.pass_avg)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.pass_td)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.pass_int)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.pass_sck)}</td>
                          <td className="player-pool-grid-num">{formatDecimal(row.pass_rtg)}</td>
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
