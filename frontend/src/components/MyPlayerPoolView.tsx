import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { fetchMyPlayerPool, fetchPlayerPool, saveMyPlayerPoolEntry } from "../api";
import type { PlayerPoolPlayer, PlayerPoolResult } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { formatOwnershipPct, formatSalary } from "./playerDisplay";

// season/week/platform come from the shared header controls (see
// App.tsx), same as every other weekly tab.
interface MyPlayerPoolViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

// Same position set/chip pattern as Ownership Summary's own Position
// filter (see OwnershipSummaryView.tsx) -- DST included since a saved
// entry can be a defense just like any other position.
const POSITIONS = ["QB", "RB", "WR", "TE", "DST"] as const;

// Always counts the full pool, not visiblePlayers -- this is a summary of
// what's actually saved, so it shouldn't shrink just because the Position
// chips currently narrow what's shown below it. Positions with zero
// players are left out rather than shown as "QB 0".
function positionCountsLabel(players: PlayerPoolPlayer[]): string {
  const counts = new Map<string, number>();
  for (const p of players) counts.set(p.position, (counts.get(p.position) ?? 0) + 1);
  const parts = POSITIONS.filter((pos) => counts.has(pos)).map((pos) => `${pos} ${counts.get(pos)}`);
  return `${players.length} player${players.length === 1 ? "" : "s"} (${parts.join(", ")})`;
}

function opponentLabel(row: PlayerPoolPlayer): string {
  return row.is_home === null ? row.opponent : row.is_home ? `vs ${row.opponent}` : `@${row.opponent}`;
}

// Click-a-column-header sorting, same pattern as Player Rankings' own
// sortable Salary/Total headers (see PlayerPoolView.tsx's toggleSort/
// sortIcon/sortAriaLabel) -- generalized here to cover both this tab's
// tables (My Players and Other Settings Player Pool players), each with
// its own independent field/direction state. "rank" means Total.
type PlayerSortField = "name" | "salary" | "ownership" | "rank";
type SortDirection = "asc" | "desc";

// null field means "no explicit sort yet" -- rows stay in whatever order
// their source list already provided (My Players' own save order, Other
// Settings Player Pool players' as-fetched order).
function sortPlayers(players: PlayerPoolPlayer[], field: PlayerSortField | null, direction: SortDirection): PlayerPoolPlayer[] {
  if (field === null) return players;
  const sorted = [...players];
  sorted.sort((a, b) => {
    let cmp: number;
    if (field === "name") cmp = a.player.localeCompare(b.player);
    else if (field === "salary") cmp = a.salary - b.salary;
    else if (field === "ownership") cmp = (a.ownership_pct ?? -1) - (b.ownership_pct ?? -1);
    else cmp = a.total - b.total;
    return direction === "asc" ? cmp : -cmp;
  });
  return sorted;
}

function sortIcon(field: PlayerSortField, currentField: PlayerSortField | null, direction: SortDirection): string {
  if (currentField !== field) return "⇅";
  return direction === "asc" ? "▲" : "▼";
}

function sortAriaLabel(
  field: PlayerSortField,
  label: string,
  currentField: PlayerSortField | null,
  direction: SortDirection
): string {
  if (currentField !== field) return `Sort by ${label}`;
  return direction === "asc" ? `Sort by ${label} descending` : `Sort by ${label} ascending`;
}

// One sortable <th> -- clicking it toggles direction if it's already the
// active column, or switches to it (starting descending, matching
// PlayerPoolView's own convention of "highest first" reading naturally
// for a DFS ranking) otherwise.
function SortableTh({
  field,
  label,
  extra,
  thClassName,
  currentField,
  direction,
  onToggle,
}: {
  field: PlayerSortField;
  label: string;
  extra?: ReactNode;
  thClassName?: string;
  currentField: PlayerSortField | null;
  direction: SortDirection;
  onToggle: (field: PlayerSortField) => void;
}) {
  return (
    <th
      className={thClassName}
      aria-sort={currentField === field ? (direction === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        className="player-pool-sort-header"
        onClick={() => onToggle(field)}
        aria-label={sortAriaLabel(field, label, currentField, direction)}
      >
        {label}
        {extra}
        <span className="player-pool-sort-icon" aria-hidden="true">
          {sortIcon(field, currentField, direction)}
        </span>
      </button>
    </th>
  );
}

// Same 8 columns everywhere a player row appears on this tab (My Players
// and Other Settings Player Pool players) -- factored out so the two
// tables can't silently drift apart. Each table supplies its own trailing
// action cell (Remove vs. Add).
function PlayerRowCells({ row }: { row: PlayerPoolPlayer }) {
  return (
    <>
      <td className="player-pool-grid-sticky">{row.player}</td>
      <td>{row.position}</td>
      <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
      <td className="player-pool-grid-num">{formatExpectedFpts(row.expected_fpts)}</td>
      <td>{row.team}</td>
      <td>{opponentLabel(row)}</td>
      <td className="player-pool-grid-num">{formatOwnershipPct(row.ownership_pct)}</td>
      <td className="player-pool-grid-num player-pool-grid-total">{formatTotal(row.total)}</td>
    </>
  );
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
  // Just the players currently checked in Settings' Player Selection
  // (apply_selection_filter=true, the default) -- backs the "Other
  // Settings Player Pool players" panel below, which only makes sense
  // once a Position filter narrows things down (see otherSettingsPlayers).
  const [settingsSelectedPlayers, setSettingsSelectedPlayers] = useState<PlayerPoolPlayer[]>([]);

  const [searchQuery, setSearchQuery] = useState("");
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(new Set());
  const [positionFilter, setPositionFilter] = useState<Set<string>>(new Set());

  // Independent sort state per table -- see SortableTh/sortPlayers above.
  const [mySortField, setMySortField] = useState<PlayerSortField | null>(null);
  const [mySortDirection, setMySortDirection] = useState<SortDirection>("desc");
  const [otherSortField, setOtherSortField] = useState<PlayerSortField | null>(null);
  const [otherSortDirection, setOtherSortDirection] = useState<SortDirection>("desc");

  function toggleMySort(field: PlayerSortField) {
    if (mySortField === field) setMySortDirection((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setMySortField(field);
      setMySortDirection("desc");
    }
  }

  function toggleOtherSort(field: PlayerSortField) {
    if (otherSortField === field) setOtherSortDirection((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setOtherSortField(field);
      setOtherSortDirection("desc");
    }
  }

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetchMyPlayerPool(season, week, platform, contest),
      fetchPlayerPool(season, week, platform, contest, false),
      fetchPlayerPool(season, week, platform, contest, true),
    ])
      .then(([poolResult, allResult, settingsResult]) => {
        setData(poolResult);
        setAllPlayers(allResult.players);
        setSettingsSelectedPlayers(settingsResult.players);
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
  const visiblePlayers = useMemo(() => {
    const filtered = positionFilter.size === 0 ? players : players.filter((p) => positionFilter.has(p.position));
    return sortPlayers(filtered, mySortField, mySortDirection);
  }, [players, positionFilter, mySortField, mySortDirection]);

  // Only surfaced once a Position filter narrows things down -- "other
  // players at this position" doesn't mean much across every position at
  // once. Settings-selected players already in this pool are left out
  // (they're already shown above), so this is purely "who else is
  // available to add." Independent of Settings' Player Selection is My
  // Player Pool's whole design (see this component's own docstring), so
  // this panel is an add-shortcut, not a suggestion that these players
  // are somehow more valid than ones Settings excluded.
  const otherSettingsPlayers = useMemo(() => {
    if (positionFilter.size === 0) return [];
    const candidates = settingsSelectedPlayers.filter(
      (p) => positionFilter.has(p.position) && !poolPlayerNames.has(p.player)
    );
    return sortPlayers(candidates, otherSortField, otherSortDirection);
  }, [settingsSelectedPlayers, positionFilter, poolPlayerNames, otherSortField, otherSortDirection]);
  const multiplierLabel = resolvedMultiplierLabel(players.length > 0 ? players : settingsSelectedPlayers);

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
          <>
            <p className="hint">{positionCountsLabel(players)}</p>
            <ChipMultiSelect label="Position" options={[...POSITIONS]} selected={positionFilter} onChange={setPositionFilter} />
          </>
        )}

        {!loading && !error && players.length > 0 && visiblePlayers.length === 0 && (
          <p className="hint">No players match the current filter.</p>
        )}

        {!loading && !error && visiblePlayers.length > 0 && (
          <div className="player-pool-grid-wrap">
            <table className="player-pool-grid">
              <thead>
                <tr>
                  <SortableTh
                    field="name"
                    label="Name"
                    thClassName="player-pool-grid-sticky"
                    currentField={mySortField}
                    direction={mySortDirection}
                    onToggle={toggleMySort}
                  />
                  <th>Pos</th>
                  <SortableTh
                    field="salary"
                    label="Salary"
                    currentField={mySortField}
                    direction={mySortDirection}
                    onToggle={toggleMySort}
                  />
                  <th>
                    Expected
                    <br />
                    FPTS ({multiplierLabel}x)
                  </th>
                  <th>Team</th>
                  <th>Opp</th>
                  <SortableTh
                    field="ownership"
                    label="Ownership"
                    currentField={mySortField}
                    direction={mySortDirection}
                    onToggle={toggleMySort}
                  />
                  <SortableTh
                    field="rank"
                    label="Rank"
                    extra={
                      <>
                        <br />
                        Total
                      </>
                    }
                    currentField={mySortField}
                    direction={mySortDirection}
                    onToggle={toggleMySort}
                  />
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {visiblePlayers.map((row) => (
                  <tr key={row.player}>
                    <PlayerRowCells row={row} />
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

        {!loading && !error && positionFilter.size > 0 && (
          <div className="my-player-pool-other-settings">
            <h3>Other Settings Player Pool players</h3>
            <p className="hint">
              Players checked in Settings' Player Selection at the current position filter, not yet in your pool.
            </p>
            {otherSettingsPlayers.length === 0 ? (
              <p className="hint">No other Settings-selected players at this position.</p>
            ) : (
              <div className="player-pool-grid-wrap">
                <table className="player-pool-grid">
                  <thead>
                    <tr>
                      <SortableTh
                        field="name"
                        label="Name"
                        thClassName="player-pool-grid-sticky"
                        currentField={otherSortField}
                        direction={otherSortDirection}
                        onToggle={toggleOtherSort}
                      />
                      <th>Pos</th>
                      <SortableTh
                        field="salary"
                        label="Salary"
                        currentField={otherSortField}
                        direction={otherSortDirection}
                        onToggle={toggleOtherSort}
                      />
                      <th>
                        Expected
                        <br />
                        FPTS ({multiplierLabel}x)
                      </th>
                      <th>Team</th>
                      <th>Opp</th>
                      <SortableTh
                        field="ownership"
                        label="Ownership"
                        currentField={otherSortField}
                        direction={otherSortDirection}
                        onToggle={toggleOtherSort}
                      />
                      <SortableTh
                        field="rank"
                        label="Rank"
                        extra={
                          <>
                            <br />
                            Total
                          </>
                        }
                        currentField={otherSortField}
                        direction={otherSortDirection}
                        onToggle={toggleOtherSort}
                      />
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {otherSettingsPlayers.map((row) => (
                      <tr key={row.player}>
                        <PlayerRowCells row={row} />
                        <td>
                          <button type="button" disabled={pendingKeys.has(row.player)} onClick={() => addPlayer(row)}>
                            Add
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>
    </>
  );
}
