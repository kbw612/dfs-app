import { matchesDepth } from "../depthFilter";
import { positionsForFilter } from "../positionFilters";
import { formatSnapshotLabel, yearFromId } from "../snapshotId";
import type { Change, ChangeValue, DiffResult } from "../types";
import { isPlayerChangeValue } from "../types";

interface DiffResultsProps {
  diff: DiffResult | null;
  positionFilter: string; // "" = no filter, show everything
  statusFilter: Set<string>; // empty = no filter, show everything
  depthFilter: Set<string>; // always active -- empty means show nothing, not "show everything"
}

function formatValue(value: ChangeValue): string {
  if (value === null) return "—";
  if (isPlayerChangeValue(value)) {
    return `${value.status ?? "healthy"} (rank ${value.rank})`;
  }
  return value;
}

// Groups by team_abbrev, then by position within each team. Team-level
// changes (field set, position null -- e.g. defensive_formation) fall
// into their own pseudo-group labeled by the field name, per
// generate_diff()'s design: "other" changes with a field never combine
// with a position.
function groupBy<T>(items: T[], keyOf: (item: T) => string): [string, T[]][] {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const key = keyOf(item);
    const bucket = map.get(key);
    if (bucket) {
      bucket.push(item);
    } else {
      map.set(key, [item]);
    }
  }
  return [...map.entries()];
}

export function DiffResults({ diff, positionFilter, statusFilter, depthFilter }: DiffResultsProps) {
  if (!diff) {
    return <p className="hint">No comparison run yet.</p>;
  }

  // Years show on both sides only when the two snapshots fall in
  // different years -- otherwise it's just noise.
  const includeYear = yearFromId(diff.from_snapshot) !== yearFromId(diff.to_snapshot);
  const fromLabel = formatSnapshotLabel(diff.from_snapshot, includeYear);
  const toLabel = formatSnapshotLabel(diff.to_snapshot, includeYear);

  if (diff.change_count === 0) {
    return (
      <p className="hint">
        No differences between {fromLabel} and {toLabel}.
      </p>
    );
  }

  // A position filter only ever matches changes that have a position --
  // team-level changes (defensive_formation, position null) never belong
  // to any of these categories, so they drop out whenever a filter is active.
  const allowedPositions = positionFilter ? positionsForFilter(positionFilter) : null;

  // Status filter matches the player's *current* status only ("who is now
  // IR", not "who used to be IR"). Only player-level changes carry a
  // status at all, so team-level changes and removed players (current ===
  // null) never match once a status filter is active.
  function matchesStatus(c: Change): boolean {
    if (statusFilter.size === 0) return true;
    return isPlayerChangeValue(c.current) && c.current.status !== null && statusFilter.has(c.current.status);
  }

  const changesToShow = diff.changes.filter((c) => {
    const positionOk = allowedPositions ? c.position !== null && allowedPositions.has(c.position) : true;
    return positionOk && matchesStatus(c) && matchesDepth(c, depthFilter);
  });

  if (changesToShow.length === 0) {
    const activeFilters: string[] = [];
    if (positionFilter) activeFilters.push(`"${positionFilter}"`);
    if (statusFilter.size > 0) activeFilters.push(`status ${[...statusFilter].join("/")}`);
    activeFilters.push(
      depthFilter.size > 0 ? `depth ${[...depthFilter].join("/")}` : "depth (no chips selected)"
    );
    return (
      <p className="hint">
        No {activeFilters.join(" + ")} changes between {fromLabel} and {toLabel}.
      </p>
    );
  }

  const teamGroups = groupBy(changesToShow, (c: Change) => c.team_abbrev ?? "Unknown team").sort(
    ([a], [b]) => a.localeCompare(b)
  );

  return (
    <div className="diff-results">
      <h2>
        {fromLabel} → {toLabel} ({changesToShow.length} change
        {changesToShow.length === 1 ? "" : "s"})
      </h2>
      {teamGroups.map(([team, teamChanges]) => {
        const positionGroups = groupBy(
          teamChanges,
          (c) => c.position ?? (c.field ? `Team (${c.field})` : "Other")
        );
        return (
          <section key={team} className="team-group">
            <h3>{team}</h3>
            {positionGroups.map(([position, positionChanges]) => (
              <div key={position} className="position-group">
                <h4>{position}</h4>
                <ul>
                  {positionChanges.map((change, i) => (
                    <li key={i}>
                      <span className="player-name">{change.player ?? change.field}</span>
                      <span className="change-types">{change.change_types.join(", ")}</span>
                      <span className="change-values">
                        {formatValue(change.previous)} → {formatValue(change.current)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}
