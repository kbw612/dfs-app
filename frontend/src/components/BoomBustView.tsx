import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchPlayerDefaults, fetchPlayerPool } from "../api";
import { BOOM_BUST_DFS_TYPE } from "../dfsTypes";
import type { PlayerPoolPlayer } from "../types";
import { formatOwnershipPct, formatSalary } from "./playerDisplay";

interface BoomBustViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

type Tier = "green" | "yellow" | "red";

// Ownership-based tiering for this tab only -- a different rule (and a
// different input) from Game Environment's own 0/0.5/1 tiering elsewhere
// in the app. null (Ownership tab hasn't been retrieved yet, or this
// player just isn't in that snapshot) gets no tier at all rather than
// defaulting to one.
function boomBustTier(ownershipPct: number | null): Tier | null {
  if (ownershipPct === null) return null;
  if (ownershipPct >= 10) return "red";
  if (ownershipPct > 5) return "yellow";
  return "green";
}

type SortMode = "tier_green_first" | "tier_yellow_first" | "tier_red_first" | "ownership_asc" | "ownership_desc";

const CANONICAL_TIER_ORDER: Tier[] = ["green", "yellow", "red"];

function tierOrderFor(mode: SortMode): Tier[] {
  const first: Tier | null =
    mode === "tier_green_first" ? "green" : mode === "tier_yellow_first" ? "yellow" : mode === "tier_red_first" ? "red" : null;
  if (first === null) return CANONICAL_TIER_ORDER;
  return [first, ...CANONICAL_TIER_ORDER.filter((t) => t !== first)];
}

// Stable sort (ties keep the incoming order) that always pushes players
// with no ownership data yet to the end, regardless of sort mode -- same
// "missing data sorts last" convention as Vegas Lines' own sorting.
function sortBoomBust(players: PlayerPoolPlayer[], mode: SortMode): PlayerPoolPlayer[] {
  const tierRank = new Map(tierOrderFor(mode).map((t, i) => [t, i]));
  return players
    .map((player, index) => ({ player, index, tier: boomBustTier(player.ownership_pct) }))
    .sort((a, b) => {
      if (a.tier === null && b.tier === null) return a.index - b.index;
      if (a.tier === null) return 1;
      if (b.tier === null) return -1;

      if (mode === "ownership_asc" || mode === "ownership_desc") {
        const aPct = a.player.ownership_pct as number;
        const bPct = b.player.ownership_pct as number;
        if (aPct === bPct) return a.index - b.index;
        return mode === "ownership_asc" ? aPct - bPct : bPct - aPct;
      }

      const aRank = tierRank.get(a.tier) ?? 0;
      const bRank = tierRank.get(b.tier) ?? 0;
      if (aRank !== bRank) return aRank - bRank;
      // Within a tier, lowest ownership first -- consistent regardless of
      // which tier is pinned to the top.
      const aPct = a.player.ownership_pct as number;
      const bPct = b.player.ownership_pct as number;
      return aPct - bPct;
    })
    .map((entry) => entry.player);
}

function opponentLabel(row: PlayerPoolPlayer): string {
  return row.is_home === null ? row.opponent : row.is_home ? `vs ${row.opponent}` : `@${row.opponent}`;
}

function formatTotal(total: number): string {
  return total % 1 === 0 ? String(total) : total.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

// Same as Player Rankings' Expected FPTS column (see PlayerPoolView.tsx) --
// a plain fantasy-points number, not currency, trimmed the same way as
// Total.
function formatExpectedFpts(value: number): string {
  return formatTotal(value);
}

// Backs the resolved Salary Multiplier out of any one row's expected_fpts
// (see PlayerPoolView.tsx's resolvedMultiplierLabel) so the header always
// reflects whatever multiplier is actually in effect, without a second
// API call.
function resolvedMultiplierLabel(players: PlayerPoolPlayer[]): string {
  const withSalary = players.find((p) => p.salary > 0);
  if (!withSalary) return "…";
  const multiplier = withSalary.expected_fpts / (withSalary.salary / 1000);
  return formatTotal(multiplier);
}

// This tab is a read-only view driven entirely by Settings' Player
// Default Factors grid (DFS Type = "Boom/Bust", see dfsTypes.ts) -- there
// are no editable scores here, just this week's ownership% for whoever's
// tagged, colored by how "chalky" they've become. DST is never eligible
// for a DFS Type tag (same scope as Volume/Talent Defaults), so it's
// filtered out here too even though fetchPlayerPool would otherwise
// include it.
export function BoomBustView({ season, week, platform, contest }: BoomBustViewProps) {
  const [players, setPlayers] = useState<PlayerPoolPlayer[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("ownership_asc");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    // apply_selection_filter=false -- a player's DFS Type tag applies
    // regardless of whether Settings' Player Selection grid has them
    // checked, same independence Player Default Factors itself relies on.
    Promise.all([fetchPlayerPool(season, week, platform, contest, false), fetchPlayerDefaults(season)])
      .then(([poolResult, defaultsResult]) => {
        const boomBustNames = new Set(
          defaultsResult.defaults.filter((d) => d.dfs_type === BOOM_BUST_DFS_TYPE).map((d) => d.player)
        );
        setPlayers(poolResult.players.filter((p) => p.position !== "DST" && boomBustNames.has(p.player)));
      })
      .catch((err) => {
        setPlayers(null);
        setError(err instanceof Error ? err.message : "Failed to load Boom/Bust players");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, contest]);

  useEffect(() => {
    load();
  }, [load]);

  const sortedPlayers = useMemo(() => sortBoomBust(players ?? [], sortMode), [players, sortMode]);

  const isNotFound = error !== null && error.includes("No DK salary file uploaded yet");

  return (
    <section className="ownership-section">
      <div className="player-pool-grid-header">
        <h2>Boom/Bust Players</h2>
      </div>
      <p className="hint">
        Everyone tagged DFS Type "Boom/Bust" in Settings' Player Default Factors grid, colored by this week's
        projected ownership.
      </p>

      {players !== null && players.length > 0 && (
        <>
          <div className="chip-filter boom-bust-sort">
            <span className="filter-label">Sort by tier</span>
            <div className="chip-row">
              <button
                type="button"
                className={`chip${sortMode === "tier_green_first" ? " selected" : ""}`}
                aria-pressed={sortMode === "tier_green_first"}
                onClick={() => setSortMode("tier_green_first")}
              >
                Green first (≤5%)
              </button>
              <button
                type="button"
                className={`chip${sortMode === "tier_yellow_first" ? " selected" : ""}`}
                aria-pressed={sortMode === "tier_yellow_first"}
                onClick={() => setSortMode("tier_yellow_first")}
              >
                Gold first (5–10%)
              </button>
              <button
                type="button"
                className={`chip${sortMode === "tier_red_first" ? " selected" : ""}`}
                aria-pressed={sortMode === "tier_red_first"}
                onClick={() => setSortMode("tier_red_first")}
              >
                Red first (≥10%)
              </button>
            </div>
          </div>
          <div className="chip-filter boom-bust-sort">
            <span className="filter-label">Sort by ownership</span>
            <div className="chip-row">
              <button
                type="button"
                className={`chip${sortMode === "ownership_asc" ? " selected" : ""}`}
                aria-pressed={sortMode === "ownership_asc"}
                onClick={() => setSortMode("ownership_asc")}
              >
                Low to high
              </button>
              <button
                type="button"
                className={`chip${sortMode === "ownership_desc" ? " selected" : ""}`}
                aria-pressed={sortMode === "ownership_desc"}
                onClick={() => setSortMode("ownership_desc")}
              >
                High to low
              </button>
            </div>
          </div>
        </>
      )}

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && (
        <p className="hint">
          No DK salary file uploaded yet for season {season} week {week} -- upload it in the Settings tab.
        </p>
      )}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && players !== null && players.length === 0 && (
        <p className="hint">
          No players tagged "Boom/Bust" yet -- set a player's DFS Type in Settings' Player Default Factors grid.
        </p>
      )}

      {!loading && !error && sortedPlayers.length > 0 && (
        <div className="player-pool-grid-wrap">
          <table className="player-pool-grid">
            <thead>
              <tr>
                <th className="player-pool-grid-sticky">Name</th>
                <th>Pos</th>
                <th>Salary</th>
                <th>
                  Expected
                  <br />
                  FPTS ({resolvedMultiplierLabel(players ?? [])}x)
                </th>
                <th>Team</th>
                <th>Opp</th>
                <th>Ownership</th>
                <th>
                  Rank
                  <br />
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedPlayers.map((row) => {
                const tier = boomBustTier(row.ownership_pct);
                return (
                  <tr key={row.player}>
                    <td className="player-pool-grid-sticky">{row.player}</td>
                    <td>{row.position}</td>
                    <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
                    <td className="player-pool-grid-num">{formatExpectedFpts(row.expected_fpts)}</td>
                    <td>{row.team}</td>
                    <td>{opponentLabel(row)}</td>
                    <td className="player-pool-grid-num">
                      <span className={tier ? `boom-bust-tier-${tier}` : undefined}>
                        {formatOwnershipPct(row.ownership_pct)}
                      </span>
                    </td>
                    <td className="player-pool-grid-num player-pool-grid-total">{formatTotal(row.total)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
