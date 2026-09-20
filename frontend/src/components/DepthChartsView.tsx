import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDepthChartLatest } from "../api";
import { positionsForFilter } from "../positionFilters";
import { statusColorClassName, statusMatchesFilter } from "../statusCodes";
import type { DepthChartSnapshot, DepthChartTeam } from "../types";
import { PositionFilterSelect } from "./PositionFilterSelect";
import { RetrieveButton } from "./RetrieveButton";
import { StatusFilter } from "./StatusFilter";
import { StatusKey } from "./StatusKey";

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

          {selectedTeamData !== null && (
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
                        {visiblePlayers.map((p, i) => (
                          <span key={p.player}>
                            {i > 0 && ", "}
                            <span className={statusColorClassName(p.status)}>
                              {p.player}
                              {p.status && <span className="depth-chart-status"> ({p.status})</span>}
                            </span>
                          </span>
                        ))}
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
