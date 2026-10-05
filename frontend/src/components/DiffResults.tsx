import { matchesDepth } from "../depthFilter";
import { positionsForFilter } from "../positionFilters";
import { formatSnapshotLabel, yearFromId } from "../snapshotId";
import { STATUS_FILTER_GROUPS, isMultiWeekOut, statusMatchesFilter } from "../statusCodes";
import type { Change, ChangeValue, DiffResult } from "../types";
import { isPlayerChangeValue } from "../types";

interface DiffResultsProps {
  diff: DiffResult | null;
  positionFilter: string; // "" = no filter, show everything
  statusFilter: Set<string>; // empty = no filter, show everything
  depthFilter: Set<string>; // always active -- empty means show nothing, not "show everything"
  // "TEAM|Player Name" keys of every Star Players-flagged (team, player) --
  // same keying as DepthChartsView.tsx's own local starKey, read-only here
  // (Star Players is edited from the Depth Charts tab, not this one).
  starredKeys: Set<string>;
}

// Same (team, player) keying as DepthChartsView.tsx's own starKey and the
// backend's StarPlayerEntry -- duplicated locally rather than shared since
// neither of those is exported (see backend/schemas/star_players/
// star_players.py's own docstring for why team+player is the right key).
function starKey(team: string, player: string): string {
  return `${team}|${player}`;
}

// Background-shaded status badge, same green/gold/red convention as Depth
// Charts and Injury Report (see statusCodes.ts's own
// statusBackgroundClassName) -- but unconditional here rather than
// starred-only for Questionable (this tab has no "starred" concept for an
// individual change row), and healthy (status null) gets its own green
// shade instead of no color at all, since this tab shows healthy and
// injured players side by side in the same list and "healthy" needs to
// read as a status at a glance rather than looking like plain, unstyled
// text. Font stays the default color -- the signal lives in the
// background, not the text, same rule Depth Charts/Injury Report use.
function compareStatusBackgroundClassName(status: string | null): string {
  if (status === null) return "status-bg-healthy";
  if (status === "Q") return "status-bg-questionable";
  if (isMultiWeekOut(status)) return "status-bg-out-multi-week";
  const outCodes = STATUS_FILTER_GROUPS.find((g) => g.key === "O")!.codes;
  if (status === "D" || outCodes.includes(status)) return "status-bg-out";
  return "";
}

// The "(rank N)" suffix is deliberately left out of the colored span --
// only the status word itself (or "healthy") takes the color, per an
// explicit "leave (rank N) [in its] current color" request.
function ChangeValueDisplay({ value }: { value: ChangeValue }) {
  if (value === null) return <>—</>;
  if (isPlayerChangeValue(value)) {
    return (
      <>
        <span className={`diff-status-badge ${compareStatusBackgroundClassName(value.status)}`}>
          {value.status ?? "healthy"}
        </span>{" "}
        (rank{" "}
        {value.rank})
      </>
    );
  }
  return <>{value}</>;
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

export function DiffResults({ diff, positionFilter, statusFilter, depthFilter, starredKeys }: DiffResultsProps) {
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
    return isPlayerChangeValue(c.current) && statusMatchesFilter(c.current.status, statusFilter);
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
                      <span className="player-name">
                        {change.player &&
                          change.team_abbrev &&
                          starredKeys.has(starKey(change.team_abbrev, change.player)) && (
                            <span className="diff-star" aria-hidden="true">
                              ★{" "}
                            </span>
                          )}
                        {change.player ?? change.field}
                      </span>
                      <span className="change-types">{change.change_types.join(", ")}</span>
                      <span className="change-values">
                        <ChangeValueDisplay value={change.previous} /> → <ChangeValueDisplay value={change.current} />
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
