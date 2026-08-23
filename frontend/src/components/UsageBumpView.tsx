import { useEffect, useState } from "react";
import { fetchUsageBumpsLatest } from "../api";
import { OFFENSIVE_FANTASY_POSITIONS } from "../positionFilters";
import { formatSnapshotLabel } from "../snapshotId";
import type { UsageBump, UsageBumpCause } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";

interface UsageBumpViewProps {
  // Bumped by App whenever a new snapshot is retrieved, from either tab.
  refreshSignal: number;
}

type SortOption = "bump-desc" | "bump-asc" | "name" | "team";

// "Position Depth" == the player's own rank within their position group.
// Unlike team/position, this is a hard cap -- there's no "All" chip and no
// unbounded state, so 5th-string-and-deeper never shows regardless of
// which of these four are checked. Starts with all four checked.
const POSITION_DEPTHS = ["1", "2", "3", "4"];

const SORT_LABELS: Record<SortOption, string> = {
  "bump-desc": "Bump (high to low)",
  "bump-asc": "Bump (low to high)",
  name: "Name (A-Z)",
  team: "Team (A-Z)",
};

// 0 is the sentinel player_out_depths value -- nobody else in the list is
// out. Anything else is the real "also out" combo, 1-indexed list
// positions, e.g. 1, 3.
function formatPlayerOutDepths(depths: number[]): string {
  if (depths.length === 1 && depths[0] === 0) {
    return "Player out depth(s): 0 (nobody else in the list is out)";
  }
  return `Player out depth(s): ${depths.join(", ")}`;
}

// Reconstructs, from the same live config data that drove the
// calculation, either the position-settings rule that applied (e.g.
// "Usage bump players by position: WR2, WR3, TE1, RB1") or a note that
// this trigger came from the curated list instead (which has no
// positional rule to show). The role label itself (e.g. "WR1") already
// shows in the cause header just above this line, so it isn't repeated
// here.
function formatSourceRule(c: UsageBumpCause): string {
  if (c.source === "curated") {
    return `Usage bump player for ${c.player}`;
  }
  return `Usage bump players by position: ${(c.source_role_positions ?? []).join(", ")}`;
}

function sortUsageBumps(usageBumps: UsageBump[], sort: SortOption): UsageBump[] {
  return [...usageBumps].sort((a, b) => {
    switch (sort) {
      case "bump-desc":
        return b.bump_score - a.bump_score;
      case "bump-asc":
        return a.bump_score - b.bump_score;
      case "name":
        return a.player.localeCompare(b.player);
      case "team":
        return (a.team_abbrev ?? "").localeCompare(b.team_abbrev ?? "");
      default:
        return 0;
    }
  });
}

export function UsageBumpView({ refreshSignal }: UsageBumpViewProps) {
  const [usageBumps, setUsageBumps] = useState<UsageBump[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [teamFilter, setTeamFilter] = useState<Set<string>>(new Set());
  const [positionFilter, setPositionFilter] = useState<Set<string>>(new Set());
  const [depthFilter, setDepthFilter] = useState<Set<string>>(new Set(POSITION_DEPTHS));
  const [minScore, setMinScore] = useState(1);
  const [sort, setSort] = useState<SortOption>("bump-desc");
  // Which rows have their "Details" breakdown expanded -- collapsed by
  // default, keyed the same way as each row's own list key so expansion
  // survives re-sorting/re-filtering.
  const [expandedMath, setExpandedMath] = useState<Set<string>>(new Set());

  function toggleMath(key: string) {
    setExpandedMath((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchUsageBumpsLatest()
      .then((result) => {
        if (cancelled) return;
        setUsageBumps(result.usage_bumps);
        setSnapshotId(result.snapshot_id);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load usage bumps");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshSignal]);

  const teamOptions = [
    ...new Set(usageBumps.map((o) => o.team_abbrev).filter((t): t is string => t !== null)),
  ].sort();

  const filtered = usageBumps.filter((o) => {
    const teamOk = teamFilter.size === 0 || (o.team_abbrev !== null && teamFilter.has(o.team_abbrev));
    // This page is restricted to offensive fantasy positions regardless of
    // the chip selection -- the chips only narrow within that set, they
    // don't widen back out to OL/DL/special teams.
    const positionOk =
      OFFENSIVE_FANTASY_POSITIONS.includes(o.position) &&
      (positionFilter.size === 0 || positionFilter.has(o.position));
    const depthOk =
      POSITION_DEPTHS.includes(String(o.rank)) && (depthFilter.size === 0 || depthFilter.has(String(o.rank)));
    const scoreOk = o.bump_score >= minScore;
    return teamOk && positionOk && depthOk && scoreOk;
  });

  const sorted = sortUsageBumps(filtered, sort);

  return (
    <>
      {error && <p className="error">{error}</p>}
      {loading && <p className="hint">Loading…</p>}

      {!loading && !error && usageBumps.length === 0 && (
        <p className="hint">No usage bumps right now -- every listed player is healthy.</p>
      )}

      {!loading && !error && usageBumps.length > 0 && (
        <>
          <p className="hint">Based on the latest depth chart ({formatSnapshotLabel(snapshotId, true)}).</p>

          <div className="filters">
            <ChipMultiSelect
              label="Filter by team"
              options={teamOptions}
              selected={teamFilter}
              onChange={setTeamFilter}
            />
            <ChipMultiSelect
              label="Filter by position"
              options={OFFENSIVE_FANTASY_POSITIONS}
              selected={positionFilter}
              onChange={setPositionFilter}
            />
            <ChipMultiSelect
              label="Position Depth"
              options={POSITION_DEPTHS}
              selected={depthFilter}
              onChange={setDepthFilter}
              showAllOption={false}
            />
            <div className="bump-controls">
              <label className="min-score-control">
                Min bump score
                <input
                  type="number"
                  min={1}
                  value={minScore}
                  onChange={(e) => setMinScore(Math.max(1, Number(e.target.value) || 1))}
                />
              </label>
              <label className="sort-control">
                Sort by
                <select value={sort} onChange={(e) => setSort(e.target.value as SortOption)}>
                  {Object.entries(SORT_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {sorted.length === 0 ? (
            <p className="hint">No players match the current filters.</p>
          ) : (
            <>
              <div className="bump-list-header">
                <span>Player</span>
                <span>Bump Value</span>
              </div>
              <ul className="bump-list">
                {sorted.map((o) => {
                  const rowKey = `${o.team_abbrev}-${o.position}-${o.player}`;
                  const mathOpen = expandedMath.has(rowKey);
                  return (
                    <li key={rowKey} className="bump-row">
                      <div
                        className="bump-row-summary"
                        role="button"
                        tabIndex={0}
                        aria-expanded={mathOpen}
                        onClick={() => toggleMath(rowKey)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleMath(rowKey);
                          }
                        }}
                      >
                        <div className="bump-row-header">
                          <span className="player-name">{o.player}</span>
                          <span className="bump-score">{o.bump_score}</span>
                        </div>
                        <div className="bump-row-meta">
                          {o.team_abbrev ?? "—"} · {o.position}
                          {o.rank}
                        </div>
                        <div className="bump-causes">
                          {o.causes
                            .map((c) => `${c.player} (${c.status}) ${c.position}${c.rank}: +${c.weight}`)
                            .join(", ")}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="bump-math-toggle"
                        onClick={() => toggleMath(rowKey)}
                        aria-expanded={mathOpen}
                      >
                        Details {mathOpen ? "▴" : "▾"}
                      </button>
                      {mathOpen && (
                        <div className="bump-math">
                          {o.causes.map((c, i) => (
                            <div key={i} className="bump-math-cause">
                              <div className="bump-math-cause-header">
                                {c.player} ({c.status}) {c.position}
                                {c.rank}
                              </div>
                              <div className="bump-math-source">{formatSourceRule(c)}</div>
                              <div className="bump-math-combo">{formatPlayerOutDepths(c.player_out_depths)}</div>
                              <table className="bump-math-table">
                                <thead>
                                  <tr>
                                    <th>Depth</th>
                                    <th>Value</th>
                                    <th>Player</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {c.usage_bump_list.map((entry) => (
                                    <tr
                                      key={entry.depth}
                                      className={entry.player === o.player ? "bump-math-row-self" : undefined}
                                    >
                                      <td>{entry.depth}</td>
                                      <td>+{entry.weight}</td>
                                      <td>
                                        {entry.player}
                                        {entry.status ? ` (${entry.status})` : ""} {entry.position}
                                        {entry.rank}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          ))}
                          <div className="bump-math-total">Total: {o.bump_score}</div>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </>
      )}
    </>
  );
}
