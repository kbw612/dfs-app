import { useEffect, useState } from "react";
import { fetchOwnershipLatest, importOwnershipCsv } from "../api";
import type {
  GameLeverageGroup,
  LeverageReason,
  MultiLeveragePlayer,
  OwnershipLatestResult,
  PivotGroup,
} from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import {
  formatOwnershipPct,
  formatSalary,
  opponentLabel,
  PlayerNameCell,
  PlayerRow,
  playerMatchesFilters,
  roleLabel,
} from "./playerDisplay";

// LeverageReason/MultiLeveragePlayer (imported from ../types) are computed
// server-side -- see engine.py's compute_multi_leverage() -- and arrive on
// data.multi_leverage already sorted (reason count descending, salary
// descending within a tie), so the frontend just renders the list as-is:
// one dense row per player (name/salary/reason-count badge, no card
// border/padding) with no "leverage for N players" group headings --
// the badge carries that info inline instead. Reasons themselves aren't
// shown in a modal; clicking a row expands them in place, same
// click-to-expand pattern as the Pivots/Game Leverage sections.
function describeReason(reason: LeverageReason): string {
  const a = reason.against;
  if (reason.kind === "pivot") {
    return `Pivot for ${a.player} ${roleLabel(a)} — ${formatOwnershipPct(a.ownership_pct)} owned, ${formatSalary(a.salary)}`;
  }
  // team/opponent are only null for kind "pivot" (see LeverageReason in
  // types.ts) -- always set by the backend for kind "game".
  return `Game leverage vs ${a.player} ${roleLabel(a)} (${formatOwnershipPct(a.ownership_pct)} owned) — ${reason.team ?? "?"} vs ${reason.opponent ?? "?"}`;
}

// season/week come from the shared header control (see App.tsx) rather
// than being owned here -- this tab just reacts to whatever's currently
// selected there.
interface OwnershipViewProps {
  season: number;
  week: number;
}

export function OwnershipView({ season, week }: OwnershipViewProps) {
  const [data, setData] = useState<OwnershipLatestResult | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [fetchLoading, setFetchLoading] = useState(false);

  const [loadLoading, setLoadLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastPlayerCount, setLastPlayerCount] = useState<number | null>(null);

  const [teamFilter, setTeamFilter] = useState<Set<string>>(new Set());
  const [positionFilter, setPositionFilter] = useState<Set<string>>(new Set());
  // Keyed by trigger player name (Pivots section), "team-opponent" (Game
  // Leverage -- one row per game, collapsed by default), or the leverage
  // player's own name (Leverage & pivot plays) -- same interaction pattern
  // throughout, click the row (or its arrow) to expand.
  const [expandedPivots, setExpandedPivots] = useState<Set<string>>(new Set());
  const [expandedGames, setExpandedGames] = useState<Set<string>>(new Set());
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
  const toggleGame = makeToggle(setExpandedGames);
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
    // season/week now come from the shared header control (see App.tsx),
    // so a change there should refetch this tab's data the same way
    // switching tabs would -- no more "type a new week, then click Load"
    // two-step for viewing an already-saved week.
    loadLatest(season, week);
  }, [season, week]);

  async function handleLoad() {
    setLoadLoading(true);
    setLoadError(null);
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

  // Already sorted by the backend (reason count desc, salary desc within a
  // tie) -- no client-side grouping or re-sorting needed, just filtering.
  const filteredMultiLeverage: MultiLeveragePlayer[] =
    data?.multi_leverage.filter((entry) => playerMatchesFilters(entry.player, teamFilter, positionFilter)) ?? [];

  return (
    <>
      <div className="ownership-load-form">
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
            <h2 className="ownership-pivot-players-heading">
              Players who are game or salary pivots against 2 or more other players
            </h2>
            {filteredMultiLeverage.length === 0 ? (
              <p className="hint">No players currently qualify under the current filters.</p>
            ) : (
              <ul className="ownership-player-list pivot-card-list">
                {filteredMultiLeverage.map((entry, index) => {
                  const key = entry.player.player;
                  const open = expandedMultiLeverage.has(key);
                  // Already sorted by reason count descending -- a plain
                  // divider (no text heading, per the "no group headings"
                  // decision) marks where the count drops from one row to
                  // the next, e.g. the ×3 rows to the ×2 rows.
                  const isNewCountGroup = index > 0 && filteredMultiLeverage[index - 1].reasons.length !== entry.reasons.length;
                  return (
                    <li key={key} className={isNewCountGroup ? "ownership-leverage-group-divider" : undefined}>
                      <div
                        className="ownership-player-row ownership-multi-leverage-row"
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
                        <PlayerNameCell player={entry.player.player} role={roleLabel(entry.player)} bubbleClick />
                        <span className="ownership-player-salary">{formatSalary(entry.player.salary)}</span>
                        <span className="ownership-player-pct">{formatOwnershipPct(entry.player.ownership_pct)}</span>
                        <span className="ownership-leverage-badge">×{entry.reasons.length}</span>
                      </div>
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
            )}
          </section>

          <section className="ownership-section">
            <h2>Chalk (high-owned)</h2>
            {filteredHighOwned.length === 0 ? (
              <p className="hint">No high-owned players match the current filters.</p>
            ) : (
              <ul className="ownership-player-list pivot-card-list">
                {filteredHighOwned.map((p) => (
                  <PlayerRow key={p.player} p={p} />
                ))}
              </ul>
            )}
          </section>

          <section className="ownership-section">
            <h2>Game Pivots</h2>
            {filteredGameLeverage.length === 0 ? (
              <p className="hint">No games with chalk or pivot candidates match the current filters.</p>
            ) : (
              <ul className="ownership-game-list">
                {filteredGameLeverage.map((g) => {
                  const gameKey = `${g.team}-${g.opponent}`;
                  const open = expandedGames.has(gameKey);
                  const pivotCount = g.pivot_candidates.length;
                  return (
                    <li key={gameKey}>
                      <div
                        className="ownership-game-summary"
                        role="button"
                        tabIndex={0}
                        aria-expanded={open}
                        onClick={() => toggleGame(gameKey)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleGame(gameKey);
                          }
                        }}
                      >
                        <span className="ownership-game-matchup">
                          {g.team} vs {g.opponent}
                        </span>
                        <span className="ownership-game-counts">
                          {g.chalk_players.length} chalk · {pivotCount} pivot{pivotCount === 1 ? "" : "s"}{" "}
                          {open ? "▴" : "▾"}
                        </span>
                      </div>
                      {open && (
                        <div className="ownership-game-detail">
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
                          {pivotCount > 0 && (
                            <div className="ownership-game-subgroup">
                              <h4>Pivots</h4>
                              <ul className="ownership-player-list">
                                {g.pivot_candidates.map((p) => (
                                  <PlayerRow key={p.player} p={p} />
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="ownership-section">
            <h2>Salary Pivots</h2>
            {filteredPivots.length === 0 ? (
              <p className="hint">No pivot groups match the current filters.</p>
            ) : (
              <ul className="ownership-pivot-groups pivot-card-list">
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
                          <PlayerNameCell player={group.trigger.player} role={roleLabel(group.trigger)} bubbleClick />
                          <span className="ownership-player-pct">{formatOwnershipPct(group.trigger.ownership_pct)}</span>
                        </div>
                        <div className="ownership-pivot-meta">
                          {opponentLabel(group.trigger)} · {formatSalary(group.trigger.salary)} · {group.pivots.length}{" "}
                          pivot{group.pivots.length === 1 ? "" : "s"} {open ? "▴" : "▾"}
                        </div>
                      </div>
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
