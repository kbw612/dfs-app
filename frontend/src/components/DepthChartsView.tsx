import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDepthChartLatest, fetchStarPlayers, setStarPlayer } from "../api";
import { positionsForFilter } from "../positionFilters";
import { statusBackgroundClassName, statusMatchesFilter } from "../statusCodes";
import type { DepthChartSnapshot, DepthChartTeam, StarPlayerEntry } from "../types";
import { PositionFilterSelect } from "./PositionFilterSelect";
import { RetrieveButton } from "./RetrieveButton";
import { StatusFilter } from "./StatusFilter";
import { StatusKey } from "./StatusKey";

// "TEAM|Player Name" -- same (team, player) keying as the backend's
// StarPlayerEntry, so two same-named players on different teams don't
// collide (see backend/schemas/star_players/star_players.py's docstring).
function starKey(team: string, player: string): string {
  return `${team}|${player}`;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

interface DepthChartsViewProps {
  // Bumped by App whenever a new depth-chart snapshot is retrieved, from
  // either this tab's own Retrieve button or Compare Depth Charts' --
  // triggers a refetch here so this tab doesn't keep showing a stale
  // snapshot after a scrape that happened while it wasn't mounted. Same
  // pattern as CompareView's own refreshSignal/onScraped props.
  refreshSignal: number;
  onScraped: () => void;
}

export function DepthChartsView({ refreshSignal, onScraped }: DepthChartsViewProps) {
  const [data, setData] = useState<DepthChartSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [positionFilter, setPositionFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  const [starPlayers, setStarPlayers] = useState<StarPlayerEntry[]>([]);

  // Independent of the depth-chart snapshot itself (a different data
  // source, keyed by (team, player) rather than tied to any one snapshot),
  // so this is fetched once on mount rather than on refreshSignal.
  useEffect(() => {
    fetchStarPlayers()
      .then((result) => setStarPlayers(result.players))
      .catch(() => {
        // Non-fatal -- the depth chart itself still renders fine with no
        // stars flagged if this fetch fails.
      });
  }, []);

  const starredKeys = useMemo(() => new Set(starPlayers.map((e) => starKey(e.team, e.player))), [starPlayers]);

  // Optimistic update, revert on failure -- same convention as Player
  // Selection's own overrides toggle.
  function handleToggleStar(team: string, player: string, currentlyStarred: boolean) {
    const nextStarred = !currentlyStarred;
    const previous = starPlayers;
    setStarPlayers((prev) =>
      nextStarred ? [...prev, { team, player }] : prev.filter((e) => !(e.team === team && e.player === player))
    );
    setStarPlayer({ team, player, starred: nextStarred })
      .then((result) => setStarPlayers(result.players))
      .catch(() => setStarPlayers(previous));
  }

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchDepthChartLatest()
      .then((result) => setData(result))
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load Depth Charts");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshSignal]);

  // All teams that resolved a real abbreviation in this snapshot, same
  // "derive the chip list from the data itself" approach as Usage Bump
  // Players' own team chips -- see that view's allTeamAbbrevs comment.
  const allTeamAbbrevs = useMemo(
    () => [...new Set((data?.teams ?? []).map((t) => t.team_abbrev).filter((t): t is string => t !== null))].sort(),
    [data]
  );

  const selectedTeamData: DepthChartTeam | null = useMemo(
    () => (selectedTeam ? data?.teams.find((t) => t.team_abbrev === selectedTeam) ?? null : null),
    [data, selectedTeam]
  );

  // null (PositionFilterSelect's "All") means no position filtering at all.
  const positionMatch = positionsForFilter(positionFilter);

  const isNotFound = error !== null && error.includes("No depth chart scraped yet");

  return (
    <section className="ownership-section">
      <h2>Depth Charts</h2>

      <RetrieveButton onScraped={onScraped} />

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && (
        <p className="hint">No depth chart scraped yet -- click "Retrieve depth chart" above.</p>
      )}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && data && (
        <>
          <p className="hint vegas-lines-timestamps">Last Updated: {formatTimestamp(data.scraped_at)}</p>

          <div className="filters">
            <div className="chip-filter">
              <span className="filter-label">Team</span>
              <div className="chip-row">
                {allTeamAbbrevs.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className={`chip${selectedTeam === t ? " selected" : ""}`}
                    aria-pressed={selectedTeam === t}
                    onClick={() => setSelectedTeam(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <PositionFilterSelect value={positionFilter} onChange={setPositionFilter} />
            <StatusFilter selected={statusFilter} onChange={setStatusFilter} />
            <StatusKey />
          </div>

          {selectedTeamData === null && <p className="hint">Select a team above to view its depth chart.</p>}

          {selectedTeamData !== null && selectedTeam !== null && (
            <div className="depth-chart-team-card">
              <h3>{selectedTeamData.team_name}</h3>
              {selectedTeamData.defensive_formation && (
                <p className="hint depth-chart-formation">{selectedTeamData.defensive_formation} defensive scheme</p>
              )}
              <ul className="depth-chart-position-list">
                {Object.entries(selectedTeamData.positions)
                  .filter(([position]) => positionMatch === null || positionMatch.has(position))
                  .map(([position, players]) => {
                    // Status filter hides non-matching players entirely --
                    // an empty selection (the default) shows everyone.
                    const visiblePlayers =
                      statusFilter.size === 0 ? players : players.filter((p) => statusMatchesFilter(p.status, statusFilter));
                    if (visiblePlayers.length === 0) return null;
                    return (
                      <li key={position} className="depth-chart-position-row">
                        <span className="depth-chart-position-label">{position}:</span>{" "}
                        {visiblePlayers.map((p, i) => {
                          const starred = starredKeys.has(starKey(selectedTeam, p.player));
                          return (
                            <span key={p.player}>
                              {i > 0 && ", "}
                              {starred && (
                                <button
                                  type="button"
                                  className="depth-chart-star-toggle depth-chart-star-toggle-active"
                                  aria-pressed={starred}
                                  aria-label={`Unstar ${p.player}`}
                                  title="Unstar this player"
                                  onClick={() => handleToggleStar(selectedTeam, p.player, starred)}
                                >
                                  ★
                                </button>
                              )}
                              <button
                                type="button"
                                className={`depth-chart-name-toggle${
                                  statusBackgroundClassName(p.status, starred) ? ` ${statusBackgroundClassName(p.status, starred)}` : ""
                                }`}
                                aria-pressed={starred}
                                aria-label={starred ? `Unstar ${p.player}` : `Mark ${p.player} as a star player`}
                                title={starred ? "Unstar this player" : "Mark as a star player"}
                                onClick={() => handleToggleStar(selectedTeam, p.player, starred)}
                              >
                                {p.player}
                                {p.status && <span className="depth-chart-status"> ({p.status})</span>}
                              </button>
                            </span>
                          );
                        })}
                      </li>
                    );
                  })}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
