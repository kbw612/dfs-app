import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDiffCompare, fetchDiffLatest, fetchStarPlayers, listSnapshots } from "../api";
import { autoDepthFilter, defaultDepthFilter, depthFilterOptions } from "../depthFilter";
import type { DiffResult, SnapshotSummary, StarPlayerEntry } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { DiffResults } from "./DiffResults";
import { PositionFilterSelect } from "./PositionFilterSelect";
import { RetrieveButton } from "./RetrieveButton";
import { SnapshotPicker } from "./SnapshotPicker";
import { StatusFilter } from "./StatusFilter";
import { StatusKey } from "./StatusKey";

interface CompareViewProps {
  // Bumped by App whenever a new snapshot is retrieved, from either tab
  // -- this view's own snapshot list needs to refetch even if the scrape
  // happened while the Usage Bump Players tab was active.
  refreshSignal: number;
  // Called after RetrieveButton's own scrape succeeds -- App bumps the
  // same refreshSignal it passes in above, so the Usage Bump Players tab
  // (which also depends on the latest depth-chart snapshot) still finds
  // out about a new one even though the button itself now lives here
  // instead of the shared header.
  onScraped: () => void;
}

export function CompareView({ refreshSignal, onScraped }: CompareViewProps) {
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [positionFilter, setPositionFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  const [depthFilter, setDepthFilter] = useState<Set<string>>(defaultDepthFilter());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Read-only here (unlike Depth Charts' own clickable toggle) -- Star
  // Players is edited from the Depth Charts tab; this just displays the
  // same gold star next to a player's name so a starred player's status
  // change stands out here too, same as Injury Report's own read-only star.
  const [starPlayers, setStarPlayers] = useState<StarPlayerEntry[]>([]);

  useEffect(() => {
    fetchStarPlayers()
      .then((result) => setStarPlayers(result.players))
      .catch(() => {
        // Comparison still works without star data -- just no stars shown.
      });
  }, []);

  const starredKeys = useMemo(() => new Set(starPlayers.map((e) => `${e.team}|${e.player}`)), [starPlayers]);

  const refreshSnapshots = useCallback(async () => {
    try {
      setSnapshots(await listSnapshots());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load snapshots");
    }
  }, []);

  useEffect(() => {
    refreshSnapshots();
  }, [refreshSnapshots, refreshSignal]);

  async function runComparison(fetchDiff: () => Promise<DiffResult>) {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchDiff();
      setDiff(result);
      // Keep the From/To calendars (and their "Selected: ..." hints) in
      // sync with whatever was actually compared -- matters most for
      // "Compare last two", which doesn't otherwise touch the picker.
      setFromId(result.from_snapshot);
      setToId(result.to_snapshot);
      // Every new comparison recomputes the depth selection from its own
      // results (1 through the deepest depth present, capped at 4, plus
      // N/A if there are any team-level/removed-player rows) -- this
      // overwrites whatever the user had manually picked for the
      // previous comparison, per the auto-select rules.
      setDepthFilter(autoDepthFilter(result));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <RetrieveButton onScraped={onScraped} />

      <SnapshotPicker
        snapshots={snapshots}
        fromId={fromId}
        toId={toId}
        onFromChange={setFromId}
        onToChange={setToId}
        onCompare={() => runComparison(() => fetchDiffCompare(fromId, toId))}
        onCompareLatest={() => runComparison(fetchDiffLatest)}
        loading={loading}
      />

      <div className="filters">
        <PositionFilterSelect value={positionFilter} onChange={setPositionFilter} />
        <StatusFilter selected={statusFilter} onChange={setStatusFilter} />
        <ChipMultiSelect
          label="Position Depth"
          options={depthFilterOptions(diff)}
          selected={depthFilter}
          onChange={setDepthFilter}
          showAllOption={false}
        />
        <StatusKey />
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="hint">Loading…</p>}

      <DiffResults
        diff={diff}
        positionFilter={positionFilter}
        statusFilter={statusFilter}
        depthFilter={depthFilter}
        starredKeys={starredKeys}
      />
    </>
  );
}
