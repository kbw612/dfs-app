import { useState } from "react";
import type { SnapshotSummary } from "../types";
import { MonthCalendar } from "./MonthCalendar";

interface SnapshotPickerProps {
  snapshots: SnapshotSummary[];
  fromId: string;
  toId: string;
  onFromChange: (id: string) => void;
  onToChange: (id: string) => void;
  onCompare: () => void;
  onCompareLatest: () => void;
  loading: boolean;
}

function monthIndex(date: Date): number {
  return date.getFullYear() * 12 + date.getMonth();
}

export function SnapshotPicker({
  snapshots,
  fromId,
  toId,
  onFromChange,
  onToChange,
  onCompare,
  onCompareLatest,
  loading,
}: SnapshotPickerProps) {
  // Both calendars' browsed month, lifted up here (rather than owned by
  // each MonthCalendar) so From's month can never be navigated past To's,
  // and To's can never be navigated before From's -- equal months are
  // fine, only passing each other is blocked.
  const [fromViewDate, setFromViewDate] = useState(() => new Date());
  const [toViewDate, setToViewDate] = useState(() => new Date());

  const fromNextDisabled = monthIndex(fromViewDate) >= monthIndex(toViewDate);
  const toPrevDisabled = monthIndex(toViewDate) <= monthIndex(fromViewDate);

  return (
    <div className="snapshot-picker">
      <div className="calendar-row">
        <MonthCalendar
          label="From"
          snapshots={snapshots}
          selectedId={fromId}
          onSelect={onFromChange}
          excludeId={toId}
          viewDate={fromViewDate}
          onViewDateChange={setFromViewDate}
          disableNext={fromNextDisabled}
        />
        <MonthCalendar
          label="To"
          snapshots={snapshots}
          selectedId={toId}
          onSelect={onToChange}
          excludeId={fromId}
          viewDate={toViewDate}
          onViewDateChange={setToViewDate}
          disablePrev={toPrevDisabled}
        />
      </div>
      <div className="picker-actions">
        <button onClick={onCompare} disabled={loading || !fromId || !toId}>
          Compare selected
        </button>
        <button onClick={onCompareLatest} disabled={loading || snapshots.length < 2}>
          Compare last two
        </button>
      </div>
      {snapshots.length === 0 && (
        <p className="hint">No snapshots yet -- click "Retrieve depth chart" above.</p>
      )}
    </div>
  );
}
