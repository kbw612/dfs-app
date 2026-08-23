import { useCallback, useEffect, useState } from "react";
import { fetchDiffCompare, fetchDiffLatest, listSnapshots } from "../api";
import { autoDepthFilter, defaultDepthFilter, depthFilterOptions } from "../depthFilter";
import type { DiffResult, SnapshotSummary } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { DiffResults } from "./DiffResults";
import { PositionFilterSelect } from "./PositionFilterSelect";
import { SnapshotPicker } from "./SnapshotPicker";
import { StatusFilter } from "./StatusFilter";
import { StatusKey } from "./StatusKey";

interface CompareViewProps {
  // Bumped by App whenever a new snapshot is retrieved, from either tab
  // -- this view's own snapshot list needs to refetch even if the scrape
  // happened while the Usage Bump Players tab was active.
  refreshSignal: number;
}

export function CompareView({ refreshSignal }: CompareViewProps) {
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [positionFilter, setPositionFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  const [depthFilter, setDepthFilter] = useState<Set<string>>(defaultDepthFilter());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

      <DiffResults diff={diff} positionFilter={positionFilter} statusFilter={statusFilter} depthFilter={depthFilter} />
    </>
  );
}
