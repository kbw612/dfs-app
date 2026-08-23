import { useMemo, useState } from "react";
import { dateKeyFromId, formatDateKey, formatSnapshotLabel, timeLabelFromId } from "../snapshotId";
import type { SnapshotSummary } from "../types";

interface MonthCalendarProps {
  label: string;
  snapshots: SnapshotSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
  // The other calendar's current selection, if any -- hidden from this
  // calendar's choices so you can't pick the same snapshot for both From
  // and To. If hiding it empties out a day entirely, that day becomes
  // unselectable here.
  excludeId?: string;
  // Which month is currently displayed -- controlled by the parent
  // (SnapshotPicker) rather than owned locally, so it can enforce the
  // From-month-can't-pass-To-month constraint across both calendars.
  viewDate: Date;
  onViewDateChange: (date: Date) => void;
  disablePrev?: boolean;
  disableNext?: boolean;
}

const WEEKDAY_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function groupByDate(snapshots: SnapshotSummary[]): Map<string, SnapshotSummary[]> {
  const map = new Map<string, SnapshotSummary[]>();
  for (const snapshot of snapshots) {
    const key = dateKeyFromId(snapshot.id);
    const bucket = map.get(key);
    if (bucket) {
      bucket.push(snapshot);
    } else {
      map.set(key, [snapshot]);
    }
  }
  return map;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function MonthCalendar({
  label,
  snapshots,
  selectedId,
  onSelect,
  excludeId,
  viewDate,
  onViewDateChange,
  disablePrev,
  disableNext,
}: MonthCalendarProps) {
  const [modalDateKey, setModalDateKey] = useState<string | null>(null);

  const selectableSnapshots = useMemo(
    () => (excludeId ? snapshots.filter((s) => s.id !== excludeId) : snapshots),
    [snapshots, excludeId]
  );
  const byDate = useMemo(() => groupByDate(selectableSnapshots), [selectableSnapshots]);
  const selectedSnapshot = snapshots.find((s) => s.id === selectedId) ?? null;

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const firstOfMonth = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstOfMonth.getDay(); i++) cells.push(null);
  for (let day = 1; day <= daysInMonth; day++) cells.push(day);
  while (cells.length % 7 !== 0) cells.push(null);

  function dateKeyFor(day: number): string {
    return `${year}-${pad2(month + 1)}-${pad2(day)}`;
  }

  function goToMonth(delta: number) {
    if (delta < 0 && disablePrev) return;
    if (delta > 0 && disableNext) return;
    onViewDateChange(new Date(year, month + delta, 1));
    setModalDateKey(null);
  }

  function handleDayClick(dateKey: string, daySnapshots: SnapshotSummary[]) {
    if (daySnapshots.length > 0) {
      setModalDateKey(dateKey);
    }
  }

  const modalSnapshots = modalDateKey ? (byDate.get(modalDateKey) ?? []) : [];

  return (
    <div className="month-calendar">
      <div className="calendar-header">
        <span className="calendar-label">{label}</span>
        <div className="calendar-nav">
          <button
            type="button"
            onClick={() => goToMonth(-1)}
            disabled={disablePrev}
            aria-label="Previous month"
          >
            ‹
          </button>
          <span>{viewDate.toLocaleString("default", { month: "long", year: "numeric" })}</span>
          <button
            type="button"
            onClick={() => goToMonth(1)}
            disabled={disableNext}
            aria-label="Next month"
          >
            ›
          </button>
        </div>
      </div>

      <div className="calendar-weekdays">
        {WEEKDAY_LABELS.map((wd) => (
          <span key={wd}>{wd}</span>
        ))}
      </div>

      <div className="calendar-grid">
        {cells.map((day, i) => {
          if (day === null) {
            return <div key={i} className="calendar-cell empty" />;
          }

          const dateKey = dateKeyFor(day);
          const daySnapshots = byDate.get(dateKey) ?? [];
          const hasSnapshots = daySnapshots.length > 0;
          const isSelectedDay = selectedSnapshot !== null && dateKeyFromId(selectedSnapshot.id) === dateKey;

          return (
            <button
              key={i}
              type="button"
              className={[
                "calendar-cell",
                hasSnapshots ? "has-data" : "no-data",
                isSelectedDay ? "selected" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              disabled={!hasSnapshots}
              onClick={() => handleDayClick(dateKey, daySnapshots)}
            >
              <span className="day-number">{day}</span>
            </button>
          );
        })}
      </div>

      <p className="calendar-selected-hint">
        {selectedSnapshot ? `Selected: ${formatSnapshotLabel(selectedSnapshot.id, true)}` : "No snapshot selected"}
      </p>

      {modalDateKey && (
        <div className="modal-backdrop" onClick={() => setModalDateKey(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span>{formatDateKey(modalDateKey, true)}</span>
              <button
                type="button"
                className="modal-close"
                onClick={() => setModalDateKey(null)}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div className="modal-times">
              {modalSnapshots.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`modal-time${s.id === selectedId ? " selected" : ""}`}
                  onClick={() => {
                    onSelect(s.id);
                    setModalDateKey(null);
                  }}
                >
                  {timeLabelFromId(s.id)}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
