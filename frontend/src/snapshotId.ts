// Snapshot ids are "YYYY-MM-DD_HHMM" (see snapshot_repo.snapshot_id_from_path
// on the backend). Every place that needs to read a piece out of one goes
// through these helpers rather than re-parsing scraped_at through the
// browser's local timezone, which would risk shifting a snapshot onto the
// wrong calendar day.

export function dateKeyFromId(id: string): string {
  return id.split("_")[0] ?? id;
}

export function timeLabelFromId(id: string): string {
  const time = id.split("_")[1] ?? "";
  if (time.length !== 4) return time;
  const hours24 = Number(time.slice(0, 2));
  const minutes = time.slice(2, 4);
  const period = hours24 >= 12 ? "PM" : "AM";
  const hours12 = hours24 % 12 === 0 ? 12 : hours24 % 12;
  return `${hours12}:${minutes} ${period}`;
}

function dateParts(id: string): { year: string; month: string; day: string } {
  const [year, month, day] = dateKeyFromId(id).split("-");
  return { year, month, day };
}

export function yearFromId(id: string): string {
  return dateParts(id).year;
}

// The one place date-part formatting happens -- "08-15" (no year,
// month/day zero-padded), or "8-15-2026" (year shown, month/day NOT
// padded -- ordinary M-D-YYYY shorthand). Every other date-formatting
// helper in this file routes through this, so changing the format here
// changes it everywhere in the UI.
function formatDateParts(year: string, month: string, day: string, includeYear: boolean): string {
  return includeYear ? `${Number(month)}-${Number(day)}-${year}` : `${month}-${day}`;
}

// Formats just the date portion -- no time. Takes either a full snapshot
// id or a bare "YYYY-MM-DD" date key (e.g. the key used to group
// snapshots by day for the calendar/modal).
export function formatDateKey(dateKeyOrId: string, includeYear: boolean): string {
  const [year, month, day] = dateKeyFromId(dateKeyOrId).split("-");
  return formatDateParts(year, month, day, includeYear);
}

// "08-15 10:59 PM" (no year) or "8-15-2026 10:59 PM" (year shown) --
// callers decide whether the year is needed, e.g. when comparing two ids
// that might fall in different years.
export function formatSnapshotLabel(id: string, includeYear: boolean): string {
  const { year, month, day } = dateParts(id);
  return `${formatDateParts(year, month, day, includeYear)} ${timeLabelFromId(id)}`;
}

// Formats a from/to pair together for display -- the year is shown on both
// sides if they fall in different years, and omitted from both if they're
// the same year.
export function formatSnapshotRange(fromId: string, toId: string): string {
  const includeYear = yearFromId(fromId) !== yearFromId(toId);
  return `${formatSnapshotLabel(fromId, includeYear)} → ${formatSnapshotLabel(toId, includeYear)}`;
}
