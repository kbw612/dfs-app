import { useEffect, useState } from "react";
import { fetchPlayerSelection, savePlayerSelectionEntry } from "../api";
import type { PlayerSelectionRow } from "../types";
import { formatSalary, opponentLabel } from "./playerDisplay";

// Mirrors Player Pool's own position filter chips (see
// PlayerPoolView.tsx's POSITIONS) -- DST is left out on purpose, this
// feature doesn't apply to it (see backend/services/player_selection/
// engine.py's docstring).
const POSITIONS = ["QB", "RB", "WR", "TE"] as const;
type Position = (typeof POSITIONS)[number];

interface PlayerSelectionGridProps {
  season: number;
  week: number;
  platform: string;
  // Bumped after a successful salary-file upload to force a refetch even
  // though season/week/platform didn't change -- a new file can mean a
  // different player universe entirely (see FileUploadStatus's
  // refreshToken for the same pattern).
  refreshToken: number;
}

// Settings panel that narrows down which QB/RB/WR/TE players from this
// week's salary file show up in Player Pool and Salary Blocks -- see
// backend/api/player_selection/latest.py. Unchecking a player saves
// immediately (no debounce -- a checkbox click is already one discrete
// edit), same as the Platform/Contest chips above it in Settings.
export function PlayerSelectionGrid({ season, week, platform, refreshToken }: PlayerSelectionGridProps) {
  const [position, setPosition] = useState<Position>("QB");
  const [players, setPlayers] = useState<PlayerSelectionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingPlayers, setSavingPlayers] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPlayerSelection(season, week, platform)
      .then((result) => {
        if (!cancelled) setPlayers(result.players);
      })
      .catch((err) => {
        if (!cancelled) {
          setPlayers([]);
          setError(err instanceof Error ? err.message : "Failed to load players");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, platform, refreshToken]);

  async function toggleSelected(row: PlayerSelectionRow) {
    const nextSelected = !row.selected;
    // Optimistic update -- the checkbox flips immediately, then the save
    // confirms in the background. Reverted below if the save fails.
    setPlayers((prev) => prev.map((p) => (p.player === row.player ? { ...p, selected: nextSelected } : p)));
    setSavingPlayers((prev) => new Set(prev).add(row.player));
    try {
      await savePlayerSelectionEntry({ season, week, platform, player: row.player, selected: nextSelected });
    } catch (err) {
      setPlayers((prev) => prev.map((p) => (p.player === row.player ? { ...p, selected: row.selected } : p)));
      setError(err instanceof Error ? err.message : "Failed to save selection");
    } finally {
      setSavingPlayers((prev) => {
        const next = new Set(prev);
        next.delete(row.player);
        return next;
      });
    }
  }

  const isNotFound = error !== null && error.includes("No DK salary file uploaded yet");
  const visiblePlayers = players
    .filter((p) => p.position === position)
    .sort((a, b) => b.salary - a.salary);

  return (
    <>
      <div className="filters">
        <div className="chip-filter">
          <span className="filter-label">Position</span>
          <div className="chip-row">
            {POSITIONS.map((p) => (
              <button
                key={p}
                type="button"
                className={`chip${position === p ? " selected" : ""}`}
                aria-pressed={position === p}
                onClick={() => setPosition(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && (
        <p className="hint">No DK salary file uploaded yet for season {season} week {week} -- upload it above.</p>
      )}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && visiblePlayers.length === 0 && <p className="hint">No {position} players loaded.</p>}

      {!loading && !error && visiblePlayers.length > 0 && (
        <div className="player-pool-grid-wrap player-selection-grid-wrap">
          <table className="player-pool-grid player-selection-grid">
            <thead>
              <tr>
                <th className="player-selection-checkbox-col"></th>
                <th className="player-pool-grid-sticky player-selection-name-col">Name</th>
                <th>Salary</th>
                <th>Team</th>
                <th>Game Info</th>
              </tr>
            </thead>
            <tbody>
              {visiblePlayers.map((row) => (
                <tr key={row.player} className={row.selected ? undefined : "player-selection-row-excluded"}>
                  <td className="player-selection-checkbox-col">
                    <label className="player-selection-checkbox-wrap">
                      <input
                        type="checkbox"
                        className="player-selection-checkbox-input"
                        checked={row.selected}
                        disabled={savingPlayers.has(row.player)}
                        onChange={() => toggleSelected(row)}
                      />
                      <span className="player-selection-checkbox-box" aria-hidden="true">
                        {row.selected && (
                          <svg width="8" height="8" viewBox="0 0 16 16">
                            <path
                              d="M3 8.5l3 3 7-7"
                              fill="none"
                              stroke="white"
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        )}
                      </span>
                    </label>
                  </td>
                  <td className="player-pool-grid-sticky player-selection-name-col">{row.player}</td>
                  <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
                  <td>{row.team}</td>
                  <td>{opponentLabel(row)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
