import { Fragment, useEffect, useMemo, useState } from "react";
import { fetchOwnershipProjections, fetchVegasLines } from "../api";
import type { OwnershipProjectionsPlayer, VegasLinesSnapshot } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { formatOwnershipPct, formatSalary, opponentLabel } from "./playerDisplay";
import { gameEnvironmentTier, tierClassName } from "./vegasLinesTiers";

// season/week/platform come from the shared header control / Settings
// panel (see App.tsx), same as every other weekly tab -- platform picks
// which uploaded Ownership file gets read (see
// backend/api/ownership/projections.py).
interface OwnershipSummaryViewProps {
  season: number;
  week: number;
  platform: string;
}

// Same position set as every other tab's chips -- DST included here since
// it's a real row in the player list (just excluded from the Team/Game
// rollups below, per an explicit design decision -- see those functions'
// docstrings).
const POSITIONS = ["QB", "RB", "WR", "TE", "DST"] as const;

type SortDirection = "desc" | "asc";

// Which ownership figure a table is currently sorted by -- every sortable
// list on this tab (Players, Ownership by team, Ownership by game) offers
// the same three, since they all now carry the same Initial/Current/Diff
// triplet.
type SortField = "initial" | "current" | "diff";

// Same alphabetically-sorted "TEAM1-TEAM2"/"TEAM1 vs TEAM2" convention as
// backend/services/ownership/position_blocks.py's game_key/game_label and
// VegasLinesView's own game grouping -- stable regardless of which side of
// the matchup a given row starts from.
function gameKey(team: string, opponent: string): string {
  return [team, opponent].sort().join("-");
}

function gameLabel(team: string, opponent: string): string {
  return [team, opponent].sort().join(" vs ");
}

interface TeamOwnership {
  team: string;
  initialTotalOwnership: number;
  totalOwnership: number;
}

interface GameOwnership {
  key: string;
  label: string;
  awayTeam: string | null;
  homeTeam: string | null;
  initialTotalOwnership: number;
  totalOwnership: number;
  // Every player in the game (any position, including DST) sorted by
  // ownership% descending -- shown when the row is expanded. Distinct
  // from totalOwnership, which excludes DST (see this function's own
  // docstring below) -- the detail list is a plain roster browse, not
  // part of that rollup calculation.
  players: OwnershipProjectionsPlayer[];
}

// Combined ownership% across every rostered player at a team/game --
// DST is deliberately excluded from both rollups (an explicit choice, not
// an oversight -- a defense's own ownership% isn't part of "how chalky is
// this team/game" the way it's used here), and a player with no
// ownership_pct yet (Ownership hasn't been retrieved this week) simply
// contributes 0 rather than being skipped, so a team/game with partial
// data still shows *some* total instead of silently vanishing from the
// list. initialTotalOwnership sums initial_ownership_pct the same way --
// a player added since the initial upload contributes 0 to it, same
// convention.
function computeTeamOwnership(players: OwnershipProjectionsPlayer[]): TeamOwnership[] {
  const totals = new Map<string, { initial: number; current: number }>();
  for (const p of players) {
    if (p.position === "DST") continue;
    if (!totals.has(p.team)) totals.set(p.team, { initial: 0, current: 0 });
    const entry = totals.get(p.team)!;
    entry.initial += p.initial_ownership_pct ?? 0;
    entry.current += p.ownership_pct ?? 0;
  }
  return [...totals.entries()].map(([team, { initial, current }]) => ({
    team,
    initialTotalOwnership: initial,
    totalOwnership: current,
  }));
}

function computeGameOwnership(players: OwnershipProjectionsPlayer[]): GameOwnership[] {
  const byKey = new Map<string, GameOwnership>();
  for (const p of players) {
    const key = gameKey(p.team, p.opponent);
    let entry = byKey.get(key);
    if (!entry) {
      entry = {
        key,
        label: gameLabel(p.team, p.opponent),
        awayTeam: null,
        homeTeam: null,
        initialTotalOwnership: 0,
        totalOwnership: 0,
        players: [],
      };
      byKey.set(key, entry);
    }
    entry.players.push(p);
    if (p.position !== "DST") {
      entry.initialTotalOwnership += p.initial_ownership_pct ?? 0;
      entry.totalOwnership += p.ownership_pct ?? 0;
    }
    if (p.is_home === true) entry.homeTeam = p.team;
    if (p.is_home === false) entry.awayTeam = p.team;
  }
  for (const entry of byKey.values()) {
    entry.players.sort((a, b) => (b.ownership_pct ?? -1) - (a.ownership_pct ?? -1));
  }
  return [...byKey.values()];
}

function formatTotalOwnership(value: number): string {
  return `${value.toFixed(1)}%`;
}

// "+3.2" / "-1.5" / "0.0" -- "-" when either side is missing (a player
// not in one of the two uploads, or a team/game total that's genuinely
// 0 - 0). Shared by the player list's per-row Diff and the Team/Game
// rollups' own Diff columns.
function formatOwnershipDelta(initial: number | null, current: number | null): string {
  if (initial === null || current === null) return "-";
  const diff = current - initial;
  const sign = diff > 0 ? "+" : "";
  return `${sign}${diff.toFixed(1)}`;
}

// Every Diff cell on this tab (player rows, both rollups, and the
// per-game detail table) gets the same red/green treatment -- green for
// ownership that rose since the initial upload, red for ownership that
// fell, and no color at all when either side is missing (nothing to
// compare, same "-" case formatOwnershipDelta itself renders) or the
// diff is exactly zero (no change either way).
function diffClassName(initial: number | null, current: number | null): string | undefined {
  if (initial === null || current === null) return undefined;
  const diff = current - initial;
  if (diff > 0) return "ownership-diff-positive";
  if (diff < 0) return "ownership-diff-negative";
  return undefined;
}

// A player row's value for whichever column it's currently sorted by.
// Diff comes back null (rather than 0) when either side is missing --
// same "can't be computed" case formatOwnershipDelta renders as "-" --
// so compareNullable below can push those rows to the bottom instead of
// treating an unknown diff as a real 0.0.
function playerSortValue(p: OwnershipProjectionsPlayer, field: SortField): number | null {
  if (field === "initial") return p.initial_ownership_pct;
  if (field === "current") return p.ownership_pct;
  if (p.initial_ownership_pct === null || p.ownership_pct === null) return null;
  return p.ownership_pct - p.initial_ownership_pct;
}

// Same idea for the Team/Game rollups -- their Initial/Current totals are
// always real numbers (they start at 0 and only ever add to it, see
// computeTeamOwnership/computeGameOwnership above), so Diff never needs
// the null case playerSortValue has to handle.
function rollupSortValue(row: { initialTotalOwnership: number; totalOwnership: number }, field: SortField): number {
  if (field === "initial") return row.initialTotalOwnership;
  if (field === "current") return row.totalOwnership;
  return row.totalOwnership - row.initialTotalOwnership;
}

// Shared comparator for every sortable list on this tab. A null (a
// player absent from one of the two uploads, so its Diff can't be
// computed) always sorts to the bottom regardless of direction -- there's
// no sensible "high" or "low" for a value that doesn't exist.
function compareNullable(a: number | null, b: number | null, direction: SortDirection): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction === "desc" ? b - a : a - b;
}

// Team abbreviation -> its own implied-total tier, from the *current*
// (live, not necessarily yet "applied" to Game Environment scoring)
// Vegas Lines data -- same rules and same underlying values the Vegas
// Lines tab itself colors team names with (see vegasLinesTiers.ts).
// Games whose team name(s) never resolved to an abbreviation (away_team/
// home_team null) simply don't get an entry -- those teams render
// uncolored here, same as everywhere else this tier can be null.
function buildTeamTiers(vegas: VegasLinesSnapshot | null) {
  const tiers = new Map<string, ReturnType<typeof gameEnvironmentTier>>();
  if (!vegas) return tiers;
  for (const game of vegas.games) {
    if (game.away_team) {
      tiers.set(game.away_team, gameEnvironmentTier(game.current.away_implied_total, game.current.over_under));
    }
    if (game.home_team) {
      tiers.set(game.home_team, gameEnvironmentTier(game.current.home_implied_total, game.current.over_under));
    }
  }
  return tiers;
}

function toggleInSet(set: Set<string>, key: string): Set<string> {
  const next = new Set(set);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

// Shared by all three panels below -- the expand/collapse icon sits right
// next to the heading text (inside the same <h2>, not pushed to the far
// edge the way .player-pool-grid-header's save-status text is elsewhere),
// and the whole header is the click target.
function CollapsibleHeader({ title, expanded, onToggle }: { title: string; expanded: boolean; onToggle: () => void }) {
  return (
    <div
      className="player-pool-grid-header ownership-summary-collapsible-header"
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      onClick={onToggle}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle();
        }
      }}
    >
      <h2>
        {title}
        <span className="ownership-summary-collapse-icon">{expanded ? "▴" : "▾"}</span>
      </h2>
    </div>
  );
}

// Shared by all three panels below -- lets each one be sorted by
// whichever of the three ownership columns (Initial/Current/Diff) matters
// right now, independent of direction (see the plain high/low chip row
// next to it). A separate control from CollapsibleHeader's expand/collapse
// since sort field and sort direction are independent axes.
function SortFieldControls({ field, onChange }: { field: SortField; onChange: (field: SortField) => void }) {
  return (
    <div className="chip-filter ownership-summary-filter">
      <span className="filter-label">Sort by</span>
      <div className="chip-row">
        <button
          type="button"
          className={`chip${field === "initial" ? " selected" : ""}`}
          aria-pressed={field === "initial"}
          onClick={() => onChange("initial")}
        >
          Initial
        </button>
        <button
          type="button"
          className={`chip${field === "current" ? " selected" : ""}`}
          aria-pressed={field === "current"}
          onClick={() => onChange("current")}
        >
          Current
        </button>
        <button
          type="button"
          className={`chip${field === "diff" ? " selected" : ""}`}
          aria-pressed={field === "diff"}
          onClick={() => onChange("diff")}
        >
          Diff
        </button>
      </div>
    </div>
  );
}

// Plain high/low direction chip row -- same shape SortFieldControls has,
// pulled out once here since Team/Game already had this control and
// Players is gaining it in this change too, all three now identical.
function SortDirectionControls({ direction, onChange }: { direction: SortDirection; onChange: (direction: SortDirection) => void }) {
  return (
    <div className="chip-filter ownership-summary-filter">
      <span className="filter-label">Direction</span>
      <div className="chip-row">
        <button
          type="button"
          className={`chip${direction === "desc" ? " selected" : ""}`}
          aria-pressed={direction === "desc"}
          onClick={() => onChange("desc")}
        >
          High to low
        </button>
        <button
          type="button"
          className={`chip${direction === "asc" ? " selected" : ""}`}
          aria-pressed={direction === "asc"}
          onClick={() => onChange("asc")}
        >
          Low to high
        </button>
      </div>
    </div>
  );
}

// This tab reads whatever's currently uploaded via Settings' Ownership
// file (fetchOwnershipProjections -- the *ownership file* itself, not the
// full DK salary slate) so it only ever lists players who actually have a
// projected ownership% for this week, same as the source spreadsheet this
// was modeled on. That's a different, newer data source from the
// Ownership Pivots tab's own mock-scrape/live-scrape snapshot (see
// backend/api/ownership/projections.py's docstring) -- there's nothing to
// "load" here, just whatever's already on disk from Settings' upload.
export function OwnershipSummaryView({ season, week, platform }: OwnershipSummaryViewProps) {
  const [players, setPlayers] = useState<OwnershipProjectionsPlayer[] | null>(null);
  const [fetchLoading, setFetchLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  // Same two timestamps Settings' Ownership file status shows (see
  // OwnershipFileStatus.tsx) -- surfaced here too so it's clear, right
  // next to the Initial/Current columns below, exactly which two uploads
  // are being compared.
  const [initialUploadedAt, setInitialUploadedAt] = useState<string | null>(null);
  const [currentUploadedAt, setCurrentUploadedAt] = useState<string | null>(null);

  const [playersExpanded, setPlayersExpanded] = useState(true);
  const [teamPanelExpanded, setTeamPanelExpanded] = useState(true);
  const [gamePanelExpanded, setGamePanelExpanded] = useState(true);
  const [positionFilter, setPositionFilter] = useState<Set<string>>(new Set());
  const [playersSortField, setPlayersSortField] = useState<SortField>("current");
  const [playersSortDirection, setPlayersSortDirection] = useState<SortDirection>("desc");
  const [teamSortField, setTeamSortField] = useState<SortField>("current");
  const [teamSort, setTeamSort] = useState<SortDirection>("desc");
  const [gameSortField, setGameSortField] = useState<SortField>("current");
  const [gameSort, setGameSort] = useState<SortDirection>("desc");
  // Individual per-game expand/collapse (inside the "Ownership by game"
  // panel) -- separate from gamePanelExpanded above, which hides/shows the
  // whole panel. Expand all/Collapse all just set this to every/no key at
  // once; a subsequent individual row click still toggles just that one
  // key, e.g. "expand all, then collapse a couple."
  const [expandedGames, setExpandedGames] = useState<Set<string>>(new Set());

  // Best-effort side data purely for team-name coloring -- a missing/
  // failed Vegas Lines fetch (nothing retrieved yet for this week) just
  // means every team renders uncolored, same as Vegas Lines' own "no
  // implied total yet" handling, rather than blocking or erroring this
  // tab's main players/team/game panels.
  const [vegasLines, setVegasLines] = useState<VegasLinesSnapshot | null>(null);

  useEffect(() => {
    setFetchLoading(true);
    setFetchError(null);
    fetchOwnershipProjections(season, week, platform)
      .then((result) => {
        setPlayers(result.players);
        setInitialUploadedAt(result.initial_uploaded_at);
        setCurrentUploadedAt(result.current_uploaded_at);
      })
      .catch((err) => {
        setPlayers(null);
        setInitialUploadedAt(null);
        setCurrentUploadedAt(null);
        // The 404 detail from GET /projections ("No ownership projections
        // file uploaded yet...") isn't a real error -- it's the expected
        // state before anyone's used Settings' Ownership file upload yet.
        setFetchError(err instanceof Error ? err.message : "Failed to load ownership data");
      })
      .finally(() => setFetchLoading(false));
  }, [season, week, platform]);

  useEffect(() => {
    fetchVegasLines(season, week)
      .then((result) => setVegasLines(result))
      .catch(() => setVegasLines(null));
  }, [season, week]);

  const teamTiers = useMemo(() => buildTeamTiers(vegasLines), [vegasLines]);

  const isNotFound = fetchError !== null && fetchError.includes("No ownership projections file uploaded yet");

  // Team/Game rollups are always computed across the full, unfiltered
  // player list -- the Position filter only narrows the player table
  // above them, per an explicit design decision (a team/game's total
  // shouldn't silently shrink just because you're currently looking at
  // one position's rows).
  const teamOwnership = useMemo(() => computeTeamOwnership(players ?? []), [players]);
  const gameOwnership = useMemo(() => computeGameOwnership(players ?? []), [players]);

  const sortedTeamOwnership = useMemo(
    () =>
      [...teamOwnership].sort((a, b) =>
        compareNullable(rollupSortValue(a, teamSortField), rollupSortValue(b, teamSortField), teamSort)
      ),
    [teamOwnership, teamSortField, teamSort]
  );

  const sortedGameOwnership = useMemo(
    () =>
      [...gameOwnership].sort((a, b) =>
        compareNullable(rollupSortValue(a, gameSortField), rollupSortValue(b, gameSortField), gameSort)
      ),
    [gameOwnership, gameSortField, gameSort]
  );

  const visiblePlayers = (players ?? [])
    .filter((p) => positionFilter.size === 0 || positionFilter.has(p.position))
    .slice()
    .sort((a, b) =>
      compareNullable(playerSortValue(a, playersSortField), playerSortValue(b, playersSortField), playersSortDirection)
    );

  function toggleGame(key: string) {
    setExpandedGames((prev) => toggleInSet(prev, key));
  }

  function expandAllGames() {
    setExpandedGames(new Set(gameOwnership.map((g) => g.key)));
  }

  function collapseAllGames() {
    setExpandedGames(new Set());
  }

  return (
    <>
      {fetchLoading && <p className="hint">Loading…</p>}
      {!fetchLoading && fetchError && isNotFound && (
        <p className="hint">
          No ownership file uploaded yet for season {season} week {week} -- upload it in the Settings tab.
        </p>
      )}
      {!fetchLoading && fetchError && !isNotFound && <p className="error">{fetchError}</p>}

      {!fetchLoading && !fetchError && players && (
        <>
          <section className="ownership-section">
            <CollapsibleHeader title="Players" expanded={playersExpanded} onToggle={() => setPlayersExpanded((v) => !v)} />
            {playersExpanded && (
              <>
                <p className="hint">
                  {players.length} players with a projected ownership% this week.
                  {initialUploadedAt && currentUploadedAt && (
                    <>
                      {" "}
                      Initial upload {new Date(initialUploadedAt).toLocaleString()}, last upload{" "}
                      {new Date(currentUploadedAt).toLocaleString()}.
                    </>
                  )}
                </p>
                <div className="ownership-summary-filter">
                  <ChipMultiSelect label="Position" options={[...POSITIONS]} selected={positionFilter} onChange={setPositionFilter} />
                </div>
                <SortFieldControls field={playersSortField} onChange={setPlayersSortField} />
                <SortDirectionControls direction={playersSortDirection} onChange={setPlayersSortDirection} />
                {visiblePlayers.length === 0 ? (
                  <p className="hint">No players match the current filter.</p>
                ) : (
                  <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
                    <table className="player-pool-grid ownership-summary-grid">
                      <thead>
                        <tr>
                          <th className="player-selection-name-col">Name</th>
                          <th>Pos</th>
                          <th>Team</th>
                          <th>Opp</th>
                          <th>Salary</th>
                          <th>Initial</th>
                          <th>Current</th>
                          <th>Diff</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visiblePlayers.map((row) => (
                          <tr key={row.player}>
                            <td className="player-selection-name-col">{row.player}</td>
                            <td>{row.position}</td>
                            <td>{row.team}</td>
                            <td>{opponentLabel(row)}</td>
                            <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
                            <td className="player-pool-grid-num">{formatOwnershipPct(row.initial_ownership_pct)}</td>
                            <td className="player-pool-grid-num">{formatOwnershipPct(row.ownership_pct)}</td>
                            <td
                              className={`player-pool-grid-num ${diffClassName(row.initial_ownership_pct, row.ownership_pct) ?? ""}`}
                            >
                              {formatOwnershipDelta(row.initial_ownership_pct, row.ownership_pct)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </section>

          <section className="ownership-section">
            <CollapsibleHeader
              title="Ownership by team"
              expanded={teamPanelExpanded}
              onToggle={() => setTeamPanelExpanded((v) => !v)}
            />
            {teamPanelExpanded && (
              <>
                <p className="hint">Combined ownership% across every rostered player on the team (DST excluded).</p>
                <SortFieldControls field={teamSortField} onChange={setTeamSortField} />
                <SortDirectionControls direction={teamSort} onChange={setTeamSort} />
                <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
                  <table className="player-pool-grid ownership-summary-grid">
                    <thead>
                      <tr>
                        <th>Team</th>
                        <th>Initial</th>
                        <th>Current</th>
                        <th>Diff</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedTeamOwnership.map((row) => (
                        <tr key={row.team}>
                          <td className={tierClassName(teamTiers.get(row.team))}>{row.team}</td>
                          <td className="player-pool-grid-num">{formatTotalOwnership(row.initialTotalOwnership)}</td>
                          <td className="player-pool-grid-num">{formatTotalOwnership(row.totalOwnership)}</td>
                          <td
                            className={`player-pool-grid-num ${diffClassName(row.initialTotalOwnership, row.totalOwnership) ?? ""}`}
                          >
                            {formatOwnershipDelta(row.initialTotalOwnership, row.totalOwnership)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>

          <section className="ownership-section">
            <CollapsibleHeader
              title="Ownership by game"
              expanded={gamePanelExpanded}
              onToggle={() => setGamePanelExpanded((v) => !v)}
            />
            {gamePanelExpanded && (
              <>
                <p className="hint">
                  Combined ownership% across every rostered player in the game (DST excluded). Click a game to see
                  its players by ownership.
                </p>
                <SortFieldControls field={gameSortField} onChange={setGameSortField} />
                <SortDirectionControls direction={gameSort} onChange={setGameSort} />
                <div className="ownership-summary-bulk-actions">
                  <button type="button" onClick={expandAllGames}>
                    Expand all
                  </button>
                  <button type="button" onClick={collapseAllGames}>
                    Collapse all
                  </button>
                </div>
                <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
                  <table className="player-pool-grid ownership-summary-grid">
                    <thead>
                      <tr>
                        <th>Game</th>
                        <th>Away</th>
                        <th>Home</th>
                        <th>Initial</th>
                        <th>Current</th>
                        <th>Diff</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedGameOwnership.map((row) => {
                        const open = expandedGames.has(row.key);
                        // row.key is the same sorted "TEAM1-TEAM2" string
                        // row.label was built from (see gameKey/gameLabel
                        // above), so splitting it back apart gives the
                        // exact two team codes the label displays, in the
                        // same order -- lets each half of "TEAM1 vs TEAM2"
                        // get its own tier color while " vs " itself stays
                        // plain text.
                        const [teamA, teamB] = row.key.split("-");
                        return (
                          <Fragment key={row.key}>
                            <tr
                              className="ownership-summary-game-row"
                              role="button"
                              tabIndex={0}
                              aria-expanded={open}
                              onClick={() => toggleGame(row.key)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  toggleGame(row.key);
                                }
                              }}
                            >
                              <td>
                                <span className={tierClassName(teamTiers.get(teamA))}>{teamA}</span> vs{" "}
                                <span className={tierClassName(teamTiers.get(teamB))}>{teamB}</span>
                              </td>
                              <td className={row.awayTeam ? tierClassName(teamTiers.get(row.awayTeam)) : undefined}>
                                {row.awayTeam ?? "-"}
                              </td>
                              <td className={row.homeTeam ? tierClassName(teamTiers.get(row.homeTeam)) : undefined}>
                                {row.homeTeam ?? "-"}
                              </td>
                              <td className="player-pool-grid-num">{formatTotalOwnership(row.initialTotalOwnership)}</td>
                              <td className="player-pool-grid-num">{formatTotalOwnership(row.totalOwnership)}</td>
                              <td
                                className={`player-pool-grid-num ${diffClassName(row.initialTotalOwnership, row.totalOwnership) ?? ""}`}
                              >
                                {formatOwnershipDelta(row.initialTotalOwnership, row.totalOwnership)}
                              </td>
                              <td className="ownership-summary-game-arrow">{open ? "▴" : "▾"}</td>
                            </tr>
                            {open && (
                              <tr className="ownership-summary-game-detail-row">
                                <td colSpan={7} className="ownership-summary-game-detail">
                                  <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
                                    <table className="player-pool-grid ownership-summary-grid">
                                      <thead>
                                        <tr>
                                          <th className="player-selection-name-col">Name</th>
                                          <th>Pos</th>
                                          <th>Team</th>
                                          <th>Salary</th>
                                          <th>Initial</th>
                                          <th>Current</th>
                                          <th>Diff</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {row.players.map((p) => (
                                          <tr key={p.player}>
                                            <td className="player-selection-name-col">{p.player}</td>
                                            <td>{p.position}</td>
                                            <td>{p.team}</td>
                                            <td className="player-pool-grid-num">{formatSalary(p.salary)}</td>
                                            <td className="player-pool-grid-num">{formatOwnershipPct(p.initial_ownership_pct)}</td>
                                            <td className="player-pool-grid-num">{formatOwnershipPct(p.ownership_pct)}</td>
                                            <td
                                              className={`player-pool-grid-num ${diffClassName(p.initial_ownership_pct, p.ownership_pct) ?? ""}`}
                                            >
                                              {formatOwnershipDelta(p.initial_ownership_pct, p.ownership_pct)}
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}
