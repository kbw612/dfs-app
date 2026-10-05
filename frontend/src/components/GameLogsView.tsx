import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { fetchGameLogs, fetchGameRecaps } from "../api";
import type { GameLogRow, GameOption, GameRecapEntry, GameRecapWeekSnapshot, TeamStatSummaryRow } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { CollapsibleHint } from "./CollapsibleHint";
import { GameRecapModal } from "./GameRecapModal";
import { HeaderInfoPopover } from "./HeaderInfoPopover";
import { PlayerStatSummaryTable } from "./PlayerStatSummaryTable";
import { MULTIPLIER_TIER_NOTES, SHARE_RANK_NOTES, statTierNotes } from "./scoringNotes";
import { TeamRecapTable } from "./TeamRecapTable";
import {
  buildGameTeamOrder,
  compareTeamsByGameOrder,
  distinctTeamWeeks,
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
  statTierClassName,
  tierClassName,
} from "./gameLogsShared";

// season/week/platform/contest come from the shared header control (see
// App.tsx), same as every other weekly tab. The DK Players tracker this
// reads from is still hardcoded to always read the All Games files (see
// DkPlayersView.tsx's own history) -- `contest` here is used only to
// narrow the Game filter/roster down to the currently-selected Contest's
// own DK salary slate (see backend/api/game_logs/game_logs.py's own
// docstring for why), not to change which tracker file is read.
interface GameLogsViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

// How long to wait after the last keystroke in the "Weeks of history"
// input before refetching -- same idea as Settings' Salary Multiplier
// debounce, just refetching instead of saving.
const LOOKBACK_DEBOUNCE_MS = 800;

interface TeamGroup {
  team: string;
  rows: GameLogRow[];
}

// Team (by this week's own game matchups, same order as Game Previews --
// see buildGameTeamOrder/compareTeamsByGameOrder) > Position (QB/RB/WR/TE
// order) > week descending, then FPTS descending within that week -- the
// "Group by position, interleaved by week" layout the user picked,
// matching the reference Google Sheet's own per-position blocks with
// multiple players' rows interleaved by week, with each week's own rows
// led by whoever scored the most that week.
function groupByTeamAndPosition(rows: GameLogRow[], teamOrder: Map<string, number>): TeamGroup[] {
  const byTeam = new Map<string, GameLogRow[]>();
  for (const row of rows) {
    if (!byTeam.has(row.team)) byTeam.set(row.team, []);
    byTeam.get(row.team)!.push(row);
  }
  const compareTeams = compareTeamsByGameOrder(teamOrder);
  return [...byTeam.entries()]
    .sort(([a], [b]) => compareTeams(a, b))
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
// TD FPTS, TD %, Opp Share, Tgt Share, Touch Share, Touches, Tgts, Rec,
// Rec Yds, Rec TD, Rush Att, Rush Yds, Rush TD, Pass Cmp, Pass Att, Pass
// Cmp%, Pass Yds, Pass Avg, Pass TD, Pass Int, Pass Sck, Pass Rtg. DST's
// own group adds one extra Sacks column right after TD % (not counted
// here since the spacer row's colSpan just needs to cover at least the
// widest group).
const GAME_LOG_COLUMN_COUNT = 32;

export function GameLogsView({ season, week, platform, contest }: GameLogsViewProps) {
  const [lookbackInput, setLookbackInput] = useState("6");
  const [lookbackWeeks, setLookbackWeeks] = useState(6);
  const lookbackDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [games, setGames] = useState<GameOption[]>([]);
  const [rows, setRows] = useState<GameLogRow[] | null>(null);
  const [teamStatSummary, setTeamStatSummary] = useState<TeamStatSummaryRow[]>([]);
  const [referenceWeek, setReferenceWeek] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Game Recaps -- one fetch per distinct week present in the currently
  // loaded rows (not per team), shared across every team's own
  // TeamRecapTable below via findTeamRecap. null = fetched, nothing
  // scraped yet for that week; absent from the map = not fetched yet.
  const [recapsByWeek, setRecapsByWeek] = useState<Map<number, GameRecapWeekSnapshot | null>>(new Map());
  const [openRecap, setOpenRecap] = useState<{ entry: GameRecapEntry; sourceUrl: string } | null>(null);

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
    fetchGameLogs(season, week, platform, lookbackWeeks, contest)
      .then((result) => {
        setRows(result.rows);
        setGames(result.games);
        setReferenceWeek(result.reference_week);
        setTeamStatSummary(result.team_stat_summary);
      })
      .catch((err) => {
        setRows(null);
        setGames([]);
        setReferenceWeek(null);
        setTeamStatSummary([]);
        setError(err instanceof Error ? err.message : "Failed to load game logs");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, contest, lookbackWeeks]);

  // Fetches Game Recaps for every distinct week present in `rows`, once
  // per week (not per team-group render) -- a small, bounded number of
  // requests (the lookback window), reused across every team via
  // findTeamRecap. Already-fetched weeks aren't re-requested on a re-render
  // caused by filter changes, only when the underlying `rows` set changes.
  useEffect(() => {
    const weeks = new Set((rows ?? []).map((r) => r.week));
    const toFetch = [...weeks].filter((w) => !recapsByWeek.has(w));
    if (toFetch.length === 0) return;
    let cancelled = false;
    Promise.all(
      toFetch.map((w) =>
        fetchGameRecaps(season, w)
          .then((snapshot): [number, GameRecapWeekSnapshot | null] => [w, snapshot])
          .catch((): [number, GameRecapWeekSnapshot | null] => [w, null])
      )
    ).then((results) => {
      if (cancelled) return;
      setRecapsByWeek((prev) => {
        const next = new Map(prev);
        for (const [w, snapshot] of results) next.set(w, snapshot);
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [rows, season, recapsByWeek]);

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

  const teamOrder = useMemo(() => buildGameTeamOrder(games), [games]);
  const groups = useMemo(() => groupByTeamAndPosition(filteredRows, teamOrder), [filteredRows, teamOrder]);

  // That team's top 2 Opp Share/Tgt Share/Touch Share values for that
  // week -- see gameLogsShared.rankTopSharesByTeamAndWeek's own docstring.
  const oppShareRanks = useMemo(
    () => rankTopSharesByTeamAndWeek(filteredRows, (r) => r.team, (r) => r.opp_share_pct),
    [filteredRows]
  );
  const targetShareRanks = useMemo(
    () => rankTopSharesByTeamAndWeek(filteredRows, (r) => r.team, (r) => r.target_share_pct),
    [filteredRows]
  );
  const touchShareRanks = useMemo(
    () => rankTopSharesByTeamAndWeek(filteredRows, (r) => r.team, (r) => r.touch_share_pct),
    [filteredRows]
  );
  // That team's top 2 Rush Yds/Rec Yds values for that week -- same
  // pattern and same green shading as the Share columns above, per an
  // explicit "follow green shading color in other columns" request.
  const rushYardsRanks = useMemo(
    () => rankTopSharesByTeamAndWeek(filteredRows, (r) => r.team, (r) => r.rush_yards),
    [filteredRows]
  );
  const receivingYardsRanks = useMemo(
    () => rankTopSharesByTeamAndWeek(filteredRows, (r) => r.team, (r) => r.receiving_yards),
    [filteredRows]
  );

  const isNotFound = error !== null && error.includes("No DK Players tracker started yet");

  return (
    <>
      <CollapsibleHint
        items={[
          `Each currently-rostered QB/RB/WR/TE/DST's own history from the last ${lookbackWeeks} week${
            lookbackWeeks === 1 ? "" : "s"
          }${referenceWeek !== null ? ` (roster as of week ${referenceWeek})` : ""}.`,
          "Salary/FPTS/Multiplier come from the DK Players tracker; Opponent/GameLoc come from the Schedule file.",
          `Touch/Tgts/Rec/etc./Opp Share/Tgt Share/Touch Share/Pass stats come from the FantasyData weekly stats
          files, computed once when "Calc Week Points & Fantasy Data" is run for that week.`,
          "Tgt Share is the player's targets divided by their team's combined pass attempts that week.",
          "Touch Share is (player carries + receptions) divided by (team carries + team receptions).",
          "Opp Share is (player carries + targets) divided by (team carries + team targets).",
          "The 9 Pass columns are QB-only.",
          `Any of those show "-" until the relevant Settings scrape exists (or, for Pass/Share columns, until Calc
          Week Points has run, or for Pass columns, for every non-QB row).`,
          "Weeks with 0 FPTS are hidden except for DST, which always shows.",
          `The Team Summary (Avg / Median) table under each team's own game outcomes sums every currently-shown
          player's own Rec/Rec Yds/Rec TD/Rush Att/Rush Yds/Rush TD/Pass Att/Pass Yds/Pass TD into a team-week
          total, then averages/medians those team totals over exactly the weeks shown below it -- a team-level
          number, not a per-player one. Computed server-side, not recomputed in the browser.`,
          "Rush Yds and Rec Yds each highlight that team's own top 2 values for the week, same green shading as Tgt/Touch Share.",
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
            <TeamRecapTable
              team={group.team}
              weeks={distinctTeamWeeks(group.rows)}
              recapsByWeek={recapsByWeek}
              onOpenRecap={(entry, sourceUrl) => setOpenRecap({ entry, sourceUrl })}
            />
            <PlayerStatSummaryTable rows={teamStatSummary.filter((r) => r.team === group.team)} />
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
                            <th>
                              Multiplier
                              <HeaderInfoPopover title="Multiplier" lines={MULTIPLIER_TIER_NOTES} />
                            </th>
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
                              <HeaderInfoPopover title="Tgt Share" lines={SHARE_RANK_NOTES} />
                            </th>
                            <th>
                              Touch
                              <br />
                              Share
                              <HeaderInfoPopover title="Touch Share" lines={SHARE_RANK_NOTES} />
                            </th>
                            <th>Touches</th>
                            <th>Tgts</th>
                            <th>Rec</th>
                            <th>
                              Rec Yds
                              <HeaderInfoPopover title="Rec Yds" lines={SHARE_RANK_NOTES} />
                            </th>
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
                              <HeaderInfoPopover title="Rush Yds" lines={SHARE_RANK_NOTES} />
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
                              <HeaderInfoPopover title="Pass Att" lines={statTierNotes(28, 38)} />
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
                              <HeaderInfoPopover title="Pass Yds" lines={statTierNotes(175, 261)} />
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
                          <td>{formatOpponent(row.opponent, row.game_location)}</td>
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
                          <td className={`player-pool-grid-num ${shareRankClassName(receivingYardsRanks.get(row))}`}>
                            {formatCount(row.receiving_yards)}
                          </td>
                          <td className="player-pool-grid-num">{formatCount(row.rec_td)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.rush_att)}</td>
                          <td className={`player-pool-grid-num ${shareRankClassName(rushYardsRanks.get(row))}`}>
                            {formatCount(row.rush_yards)}
                          </td>
                          <td className="player-pool-grid-num">{formatCount(row.rush_td)}</td>
                          <td className="player-pool-grid-num">{formatCount(row.pass_cmp)}</td>
                          <td className={`player-pool-grid-num ${statTierClassName(row.pass_att_tier)}`}>
                            {formatCount(row.pass_att)}
                          </td>
                          <td className="player-pool-grid-num">{formatPct(row.pass_cmp_pct)}</td>
                          <td className={`player-pool-grid-num ${statTierClassName(row.pass_yds_tier)}`}>
                            {formatCount(row.pass_yds)}
                          </td>
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

      {openRecap && (
        <GameRecapModal entry={openRecap.entry} sourceUrl={openRecap.sourceUrl} onClose={() => setOpenRecap(null)} />
      )}
    </>
  );
}
