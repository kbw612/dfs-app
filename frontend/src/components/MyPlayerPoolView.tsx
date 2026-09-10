import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchMyPlayerPool, fetchPlayerPool, saveMyPlayerPoolEntry } from "../api";
import type { PlayerPoolPlayer, PlayerPoolResult } from "../types";
import { formatOwnershipPct, formatSalary } from "./playerDisplay";

// season/week/platform come from the shared header controls (see
// App.tsx), same as every other weekly tab.
interface MyPlayerPoolViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
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

// This tab's own personal shortlist -- fully independent of Settings'
// Player Selection narrowing (see backend/api/my_player_pool/latest.py's
// docstring). It's read-mostly: scores are still edited on Player
// Rankings, this tab is just "which players am I taking to my optimizer"
// plus a name-search box to add someone without hunting for their row on
// Player Rankings first.
export function MyPlayerPoolView({ season, week, platform, contest }: MyPlayerPoolViewProps) {
  const [data, setData] = useState<PlayerPoolResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The full, unfiltered week's player universe -- fetched once per
  // (season, week, platform) alongside the pool itself, purely to power
  // the search-add box's client-side name filter (see searchResults
  // below). apply_selection_filter=false: My Player Pool can add a
  // player regardless of whether Player Selection has them checked.
  const [allPlayers, setAllPlayers] = useState<PlayerPoolPlayer[]>([]);

  const [searchQuery, setSearchQuery] = useState("");
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(new Set());

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchMyPlayerPool(season, week, platform, contest), fetchPlayerPool(season, week, platform, contest, false)])
      .then(([poolResult, allResult]) => {
        setData(poolResult);
        setAllPlayers(allResult.players);
      })
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load My Player Pool");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, contest]);

  useEffect(() => {
    load();
  }, [load]);

  const poolPlayerNames = useMemo(() => new Set((data?.players ?? []).map((p) => p.player)), [data]);

  const searchResults = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (query === "") return [];
    return allPlayers
      .filter((p) => !poolPlayerNames.has(p.player) && p.player.toLowerCase().includes(query))
      .slice(0, 8);
  }, [searchQuery, allPlayers, poolPlayerNames]);

  async function addPlayer(row: PlayerPoolPlayer) {
    setPendingKeys((prev) => new Set(prev).add(row.player));
    try {
      await saveMyPlayerPoolEntry({ season, week, platform, contest, player: row.player, in_pool: true });
      setData((prev) => {
        const base = prev ?? { players: [], games: [], game_environment: [] };
        return { ...base, players: [...base.players, row].sort((a, b) => b.total - a.total) };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add player");
    } finally {
      setPendingKeys((prev) => {
        const next = new Set(prev);
        next.delete(row.player);
        return next;
      });
    }
  }

  async function removePlayer(player: string) {
    setPendingKeys((prev) => new Set(prev).add(player));
    try {
      await saveMyPlayerPoolEntry({ season, week, platform, contest, player, in_pool: false });
      setData((prev) => (prev ? { ...prev, players: prev.players.filter((p) => p.player !== player) } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove player");
    } finally {
      setPendingKeys((prev) => {
        const next = new Set(prev);
        next.delete(player);
        return next;
      });
    }
  }

  const isNotFound = error !== null && error.includes("No DK salary file uploaded yet");
  const players = data?.players ?? [];

  return (
    <>
      <section className="ownership-section">
        <div className="player-pool-grid-header">
          <h2>My Player Pool</h2>
        </div>
        <p className="hint">
          Your own shortlist for this week -- independent of Settings' Player Selection. Search below to add a
          player, or check "My Pool" on the Player Rankings tab.
        </p>

        <div className="my-player-pool-search">
          <input
            type="text"
            placeholder="Search players to add…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchResults.length > 0 && (
            <ul className="my-player-pool-search-results">
              {searchResults.map((row) => (
                <li key={row.player}>
                  <span>
                    {row.player} <span className="hint">({row.position} · {row.team} · {formatSalary(row.salary)})</span>
                  </span>
                  <button type="button" disabled={pendingKeys.has(row.player)} onClick={() => addPlayer(row)}>
                    Add
                  </button>
                </li>
              ))}
            </ul>
          )}
          {searchQuery.trim() !== "" && searchResults.length === 0 && (
            <p className="hint">No matching players (or they're already in your pool).</p>
          )}
        </div>
      </section>

      <section className="ownership-section">
        {loading && <p className="hint">Loading…</p>}
        {!loading && error && isNotFound && (
          <p className="hint">
            No DK salary file uploaded yet for season {season} week {week} -- upload it in the Settings tab.
          </p>
        )}
        {!loading && error && !isNotFound && <p className="error">{error}</p>}

        {!loading && !error && players.length === 0 && (
          <p className="hint">No players in My Player Pool yet -- search above to add one.</p>
        )}

        {!loading && !error && players.length > 0 && (
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
                    FPTS ({resolvedMultiplierLabel(players)}x)
                  </th>
                  <th>Team</th>
                  <th>Opp</th>
                  <th>Ownership</th>
                  <th>
                    Rank
                    <br />
                    Total
                  </th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {players.map((row) => (
                  <tr key={row.player}>
                    <td className="player-pool-grid-sticky">{row.player}</td>
                    <td>{row.position}</td>
                    <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
                    <td className="player-pool-grid-num">{formatExpectedFpts(row.expected_fpts)}</td>
                    <td>{row.team}</td>
                    <td>{opponentLabel(row)}</td>
                    <td className="player-pool-grid-num">{formatOwnershipPct(row.ownership_pct)}</td>
                    <td className="player-pool-grid-num player-pool-grid-total">{formatTotal(row.total)}</td>
                    <td>
                      <button type="button" disabled={pendingKeys.has(row.player)} onClick={() => removePlayer(row.player)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
