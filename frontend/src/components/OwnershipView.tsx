import { useEffect, useState } from "react";
import { fetchOwnershipLatest, importOwnershipCsv } from "../api";
import type {
  GameLeverageGroup,
  LeverageReason,
  MultiLeveragePlayer,
  OwnershipLatestResult,
  OwnershipPlayer,
  PivotGroup,
} from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";

// Season/week are manual-entry in v1 (no schedule data to derive them from
// yet -- see the design doc's "Manual entry in the UI" decision), so the
// last values used are remembered here rather than in App's shared state --
// nothing else in the app needs them.
const SEASON_KEY = "dfs-app.ownership.season";
const WEEK_KEY = "dfs-app.ownership.week";

function readStoredNumber(key: string, fallback: number): number {
  const raw = localStorage.getItem(key);
  const parsed = raw === null ? NaN : Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatSalary(salary: number): string {
  return `$${salary.toLocaleString()}`;
}

// "vs OPP" / "@OPP" mirrors how the original DK export denoted home/away
// (an "@" prefix on the Opponent column) -- is_home is only null if a row
// couldn't be parsed as either, which shouldn't happen via the CSV loader
// but is defensive against a live scrape hitting an unexpected page shape.
function opponentLabel(p: OwnershipPlayer): string {
  if (p.is_home === null) return p.opponent;
  return p.is_home ? `vs ${p.opponent}` : `@${p.opponent}`;
}

// "RB1" -- position + depth-chart rank, cross-referenced server-side from
// the latest depth-chart snapshot by player name (see backend/services/
// ownership/depth_rank.py). Falls back to just the position when there's
// no depth-chart snapshot yet or this name didn't match one.
function roleLabel(p: OwnershipPlayer): string {
  return p.rank !== null ? `${p.position}${p.rank}` : p.position;
}

function playerMatchesFilters(p: OwnershipPlayer, teamFilter: Set<string>, positionFilter: Set<string>): boolean {
  const teamOk = teamFilter.size === 0 || teamFilter.has(p.team);
  const positionOk = positionFilter.size === 0 || positionFilter.has(p.position);
  return teamOk && positionOk;
}

// LeverageReason/MultiLeveragePlayer (imported from ../types) are now
// computed server-side -- see engine.py's compute_multi_leverage() -- and
// arrive ready-to-render on data.multi_leverage. All that's left here is
// display: bucketing by reason count (groupMultiLeveragePlayers) and
// formatting each reason as a sentence (describeReason), matching how
// DiffResults.tsx groups its own flat backend list by team/position for
// display rather than the backend doing it.
interface MultiLeverageGroup {
  reasonCount: number;
  players: MultiLeveragePlayer[];
}

// Buckets by reason count (3 reasons, 2 reasons, ...) -- most reasons
// first -- and sorts each bucket by salary, highest first.
function groupMultiLeveragePlayers(players: MultiLeveragePlayer[]): MultiLeverageGroup[] {
  const byCount = new Map<number, MultiLeveragePlayer[]>();
  for (const entry of players) {
    const count = entry.reasons.length;
    const bucket = byCount.get(count);
    if (bucket) {
      bucket.push(entry);
    } else {
      byCount.set(count, [entry]);
    }
  }

  return [...byCount.entries()]
    .sort(([a], [b]) => b - a)
    .map(([reasonCount, group]) => ({
      reasonCount,
      players: [...group].sort((a, b) => b.player.salary - a.player.salary),
    }));
}

function describeReason(reason: LeverageReason): string {
  const a = reason.against;
  if (reason.kind === "pivot") {
    return `Pivot for ${a.player} ${roleLabel(a)} — ${a.ownership_pct.toFixed(1)}% owned, ${formatSalary(a.salary)}`;
  }
  // team/opponent are only null for kind "pivot" (see LeverageReason in
  // types.ts) -- always set by the backend for kind "game".
  return `Game leverage vs ${a.player} ${roleLabel(a)} (${a.ownership_pct.toFixed(1)}% owned) — ${reason.team ?? "?"} vs ${reason.opponent ?? "?"}`;
}

// Name + role badge, reused by PlayerRow's grid rows and the Pivots
// section's trigger header. Its width comes entirely from whichever parent
// it's in: PlayerRow's rows are a CSS grid with a fixed 200px name column
// (see .ownership-player-row), so this stretches to fill that and
// truncates with "..." if the name doesn't fit; the Pivots trigger header
// is a plain flex row instead, so there it just sizes to the name's own
// content ("dynamic width"). The role badge (e.g. "RB1") sits outside the
// truncated span so it's never the part that gets clipped. Click (or
// Enter/Space) toggles showing the full name, wrapped onto extra lines
// within the same column rather than growing past it -- stopPropagation
// matters here because this sits inside rows that have their own
// click-to-expand behavior (the Pivots section's trigger row), so without
// it, clicking the name would also toggle that row's pivot list.
function PlayerNameCell({ player, role }: { player: string; role: string }) {
  const [expanded, setExpanded] = useState(false);

  function toggle(e: { stopPropagation: () => void }) {
    e.stopPropagation();
    setExpanded((v) => !v);
  }

  return (
    <span
      className={`ownership-player-name-wrap${expanded ? " expanded" : ""}`}
      role="button"
      tabIndex={0}
      title={player}
      onClick={toggle}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggle(e);
        }
      }}
    >
      <span className="ownership-player-name">{player}</span>
      <span className="ownership-role">{role}</span>
    </span>
  );
}

// Shared row for every player list in this view (Chalk, Game Leverage's
// chalk/pivot-candidate subgroups, and each pivot group's own pivot list).
// A CSS grid with fixed-width name/salary/pct tracks (see
// .ownership-player-row) -- unlike flexbox's proportional shrinking, fixed
// grid tracks can't drift row-to-row depending on how much a given row's
// content happens to overflow, so salary/ownership% always start at the
// exact same x-position no matter what's in the name column. The pivot
// list used to also show each candidate's own team+opponent here (they can
// be in a different game than their trigger), but that read as its own
// "team playing" column and extra whitespace -- dropped in favor of just
// name/salary/ownership%, matching every other list in this view. The
// trigger's own matchup still shows once, in its header (see
// .ownership-pivot-meta).
function PlayerRow({ p }: { p: OwnershipPlayer }) {
  return (
    <li className="ownership-player-row">
      <PlayerNameCell player={p.player} role={roleLabel(p)} />
      <span className="ownership-player-salary">{formatSalary(p.salary)}</span>
      <span className="ownership-player-pct">{p.ownership_pct.toFixed(1)}%</span>
    </li>
  );
}

export function OwnershipView() {
  const [season, setSeason] = useState(() => readStoredNumber(SEASON_KEY, new Date().getFullYear()));
  const [week, setWeek] = useState(() => readStoredNumber(WEEK_KEY, 1));

  const [data, setData] = useState<OwnershipLatestResult | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [fetchLoading, setFetchLoading] = useState(false);

  const [loadLoading, setLoadLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastPlayerCount, setLastPlayerCount] = useState<number | null>(null);

  const [teamFilter, setTeamFilter] = useState<Set<string>>(new Set());
  const [positionFilter, setPositionFilter] = useState<Set<string>>(new Set());
  // Keyed by trigger player name (Pivots section) or "team-opponent" (Game
  // Leverage's pivot-candidates subgroup) -- both collapsed by default,
  // same interaction pattern (click row or the arrow button to expand).
  const [expandedPivots, setExpandedPivots] = useState<Set<string>>(new Set());
  const [expandedGamePivots, setExpandedGamePivots] = useState<Set<string>>(new Set());
  const [expandedMultiLeverage, setExpandedMultiLeverage] = useState<Set<string>>(new Set());

  function makeToggle(setter: (updater: (prev: Set<string>) => Set<string>) => void) {
    return (key: string) => {
      setter((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
        }
        return next;
      });
    };
  }

  const togglePivot = makeToggle(setExpandedPivots);
  const toggleGamePivots = makeToggle(setExpandedGamePivots);
  const toggleMultiLeverage = makeToggle(setExpandedMultiLeverage);

  // Loads whatever's already on disk for the stored (season, week) as soon
  // as the tab is opened -- doesn't require clicking "Load" every time,
  // only when there's genuinely nothing there yet (404) or new data needs
  // importing.
  function loadLatest(s: number, w: number) {
    setFetchLoading(true);
    setFetchError(null);
    fetchOwnershipLatest(s, w)
      .then((result) => setData(result))
      .catch((err) => {
        setData(null);
        const message = err instanceof Error ? err.message : "Failed to load ownership data";
        // The 404 detail from GET /latest ("No ownership snapshots yet for
        // season X week Y...") isn't a real error -- it's the expected
        // first-visit state, so it renders as a hint instead of red text.
        setFetchError(message);
      })
      .finally(() => setFetchLoading(false));
  }

  useEffect(() => {
    loadLatest(season, week);
    // Only re-run for the initial mount -- Load/refresh below re-fetch
    // explicitly instead of relying on this effect re-firing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleLoad() {
    setLoadLoading(true);
    setLoadError(null);
    localStorage.setItem(SEASON_KEY, String(season));
    localStorage.setItem(WEEK_KEY, String(week));
    try {
      const result = await importOwnershipCsv(season, week);
      setLastPlayerCount(result.player_count);
      loadLatest(season, week);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoadLoading(false);
    }
  }

  const isNotFound = fetchError !== null && fetchError.includes("No ownership snapshots yet");

  const teamOptions = data ? [...new Set(data.players.map((p) => p.team))].sort() : [];
  const positionOptions = data ? [...new Set(data.players.map((p) => p.position))].sort() : [];

  const filteredHighOwned = data?.high_owned.filter((p) => playerMatchesFilters(p, teamFilter, positionFilter)) ?? [];

  const filteredGameLeverage: GameLeverageGroup[] =
    data?.game_leverage
      .map((g) => ({
        ...g,
        chalk_players: g.chalk_players.filter((p) => playerMatchesFilters(p, teamFilter, positionFilter)),
        pivot_candidates: g.pivot_candidates.filter((p) => playerMatchesFilters(p, teamFilter, positionFilter)),
      }))
      .filter((g) => g.chalk_players.length > 0 || g.pivot_candidates.length > 0) ?? [];

  const filteredPivots: PivotGroup[] =
    data?.pivots.filter((group) => playerMatchesFilters(group.trigger, teamFilter, positionFilter)) ?? [];

  const filteredMultiLeverage: MultiLeverageGroup[] = data
    ? groupMultiLeveragePlayers(
        data.multi_leverage.filter((entry) => playerMatchesFilters(entry.player, teamFilter, positionFilter))
      )
    : [];

  return (
    <>
      <div className="ownership-load-form">
        <label>
          Season
          <input
            type="number"
            value={season}
            onChange={(e) => setSeason(Number(e.target.value) || season)}
          />
        </label>
        <label>
          Week
          <input type="number" min={1} max={18} value={week} onChange={(e) => setWeek(Number(e.target.value) || week)} />
        </label>
        <button type="button" onClick={handleLoad} disabled={loadLoading}>
          {loadLoading ? "Loading…" : "Load ownership data"}
        </button>
      </div>
      {loadError && <p className="error">{loadError}</p>}
      {!loadError && lastPlayerCount !== null && <p className="hint">Loaded {lastPlayerCount} players.</p>}

      {fetchLoading && <p className="hint">Loading…</p>}

      {!fetchLoading && fetchError && isNotFound && (
        <p className="hint">
          No ownership data loaded yet for season {season} week {week} -- click "Load ownership data" above.
        </p>
      )}
      {!fetchLoading && fetchError && !isNotFound && <p className="error">{fetchError}</p>}

      {!fetchLoading && data && (
        <>
          <p className="hint">
            Week {data.week}, {data.season} · {data.players.length} players · leverage point {data.leverage_point}%
            ownership
          </p>

          <div className="filters">
            <ChipMultiSelect label="Filter by team" options={teamOptions} selected={teamFilter} onChange={setTeamFilter} />
            <ChipMultiSelect
              label="Filter by position"
              options={positionOptions}
              selected={positionFilter}
              onChange={setPositionFilter}
            />
          </div>

          <section className="ownership-section">
            <h2>Leverage &amp; pivot plays</h2>
            <p className="hint">Players who provide leverage or a pivot against 2 or more other players.</p>
            {filteredMultiLeverage.length === 0 ? (
              <p className="hint">No players currently qualify under the current filters.</p>
            ) : (
              filteredMultiLeverage.map((group) => (
                <div key={group.reasonCount} className="ownership-leverage-count-group">
                  <h3>Leverage/pivot for {group.reasonCount} players</h3>
                  <ul className="ownership-pivot-groups">
                    {group.players.map((entry) => {
                      const key = entry.player.player;
                      const open = expandedMultiLeverage.has(key);
                      return (
                        <li key={key} className="ownership-pivot-group">
                          <div
                            className="ownership-pivot-summary"
                            role="button"
                            tabIndex={0}
                            aria-expanded={open}
                            onClick={() => toggleMultiLeverage(key)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                toggleMultiLeverage(key);
                              }
                            }}
                          >
                            <div className="ownership-pivot-header">
                              <PlayerNameCell player={entry.player.player} role={roleLabel(entry.player)} />
                              <span className="ownership-player-salary">{formatSalary(entry.player.salary)}</span>
                            </div>
                          </div>
                          <button
                            type="button"
                            className="ownership-pivot-toggle"
                            onClick={() => toggleMultiLeverage(key)}
                            aria-expanded={open}
                          >
                            Reasons {open ? "▴" : "▾"}
                          </button>
                          {open && (
                            <ul className="ownership-leverage-reasons">
                              {entry.reasons.map((reason, i) => (
                                <li key={i} className="ownership-leverage-reason">
                                  {describeReason(reason)}
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))
            )}
          </section>

          <section className="ownership-section">
            <h2>Chalk (high-owned)</h2>
            {filteredHighOwned.length === 0 ? (
              <p className="hint">No high-owned players match the current filters.</p>
            ) : (
              <ul className="ownership-player-list">
                {filteredHighOwned.map((p) => (
                  <PlayerRow key={p.player} p={p} />
                ))}
              </ul>
            )}
          </section>

          <section className="ownership-section">
            <h2>Game leverage</h2>
            {filteredGameLeverage.length === 0 ? (
              <p className="hint">No games with chalk or pivot candidates match the current filters.</p>
            ) : (
              filteredGameLeverage.map((g) => {
                const gameKey = `${g.team}-${g.opponent}`;
                const pivotsOpen = expandedGamePivots.has(gameKey);
                return (
                  <div key={gameKey} className="ownership-game-group">
                    <h3>
                      {g.team} vs {g.opponent}
                    </h3>
                    {g.chalk_players.length > 0 && (
                      <div className="ownership-game-subgroup">
                        <h4>Chalk</h4>
                        <ul className="ownership-player-list">
                          {g.chalk_players.map((p) => (
                            <PlayerRow key={p.player} p={p} />
                          ))}
                        </ul>
                      </div>
                    )}
                    {g.pivot_candidates.length > 0 && (
                      <div className="ownership-game-subgroup">
                        <button
                          type="button"
                          className="ownership-pivot-toggle"
                          onClick={() => toggleGamePivots(gameKey)}
                          aria-expanded={pivotsOpen}
                        >
                          Pivots {pivotsOpen ? "▴" : "▾"}
                        </button>
                        {pivotsOpen && (
                          <ul className="ownership-player-list">
                            {g.pivot_candidates.map((p) => (
                              <PlayerRow key={p.player} p={p} />
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </section>

          <section className="ownership-section">
            <h2>Pivots</h2>
            {filteredPivots.length === 0 ? (
              <p className="hint">No pivot groups match the current filters.</p>
            ) : (
              <ul className="ownership-pivot-groups">
                {filteredPivots.map((group) => {
                  const key = group.trigger.player;
                  const open = expandedPivots.has(key);
                  return (
                    <li key={key} className="ownership-pivot-group">
                      <div
                        className="ownership-pivot-summary"
                        role="button"
                        tabIndex={0}
                        aria-expanded={open}
                        onClick={() => togglePivot(key)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            togglePivot(key);
                          }
                        }}
                      >
                        <div className="ownership-pivot-header">
                          <PlayerNameCell player={group.trigger.player} role={roleLabel(group.trigger)} />
                          <span className="ownership-player-pct">{group.trigger.ownership_pct.toFixed(1)}%</span>
                        </div>
                        <div className="ownership-pivot-meta">
                          {opponentLabel(group.trigger)} · {formatSalary(group.trigger.salary)}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="ownership-pivot-toggle"
                        onClick={() => togglePivot(key)}
                        aria-expanded={open}
                      >
                        Pivots {open ? "▴" : "▾"}
                      </button>
                      {open && (
                        <ul className="ownership-player-list ownership-pivot-list">
                          {group.pivots.map((p) => (
                            <PlayerRow key={p.player} p={p} />
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}
    </>
  );
}
