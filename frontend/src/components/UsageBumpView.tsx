import { useEffect, useState } from "react";
import { fetchPlayerPool, fetchUsageBumpsLatest } from "../api";
import { OFFENSIVE_FANTASY_POSITIONS } from "../positionFilters";
import { formatSnapshotLabel } from "../snapshotId";
import type { UsageBump, UsageBumpCause } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";

interface UsageBumpViewProps {
  // Bumped by App whenever a new snapshot is retrieved, from either tab.
  refreshSignal: number;
  // Used only to resolve the currently selected Contest's own team list
  // (see contestTeams below) -- the usage bump scores themselves come from
  // the depth-chart snapshot alone, same as before, not from any of these.
  season: number;
  week: number;
  platform: string;
  contest: string;
}

type ContestScope = "contest" | "allGames";

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
    return `Usage bump players for ${c.player}`;
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

export function UsageBumpView({ refreshSignal, season, week, platform, contest }: UsageBumpViewProps) {
  const [usageBumps, setUsageBumps] = useState<UsageBump[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Which teams belong to the currently selected Contest's own DK salary
  // slate -- fetched unfiltered by My Pool selection (applySelectionFilter
  // = false) since this is only used to narrow by team, not to reproduce
  // Player Rankings' own pool. null means "not resolved yet" (still
  // loading, or no Salary File uploaded for this contest) -- selecting the
  // "Contest" scope falls back to showing every team in that case rather
  // than a misleadingly empty list (see scopedUsageBumps below).
  const [contestTeams, setContestTeams] = useState<Set<string> | null>(null);
  const [contestTeamsError, setContestTeamsError] = useState<string | null>(null);
  // Defaults to "Contest" -- most usage bump review happens in the context
  // of a specific contest's slate; switch to "All Games" to see the full
  // league-wide list instead.
  const [contestScope, setContestScope] = useState<ContestScope>("contest");

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

  useEffect(() => {
    let cancelled = false;
    fetchPlayerPool(season, week, platform, contest, false)
      .then((result) => {
        if (cancelled) return;
        setContestTeams(new Set(result.players.map((p) => p.team)));
        setContestTeamsError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setContestTeams(null);
        setContestTeamsError(err instanceof Error ? err.message : "Failed to load this contest's teams");
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, platform, contest]);

  // Narrowed to the selected Contest's own teams first (when that scope is
  // chosen and resolved) -- teamOptions/filtered/sorted below all build on
  // this rather than the raw fetch, so the Team filter's own chip list
  // only ever offers teams that both (a) are on this contest's slate and
  // (b) actually have a usage bump entry right now, per the "Teams filter
  // shows teams with usage bump players listed" requirement.
  const scopedUsageBumps =
    contestScope === "contest" && contestTeams !== null
      ? usageBumps.filter((o) => o.team_abbrev !== null && contestTeams.has(o.team_abbrev))
      : usageBumps;

  const teamOptions = [
    ...new Set(scopedUsageBumps.map((o) => o.team_abbrev).filter((t): t is string => t !== null)),
  ].sort();

  const filtered = scopedUsageBumps.filter((o) => {
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
            <div className="chip-filter">
              <span className="filter-label">Contest</span>
              <div className="chip-row">
                <button
                  type="button"
                  className={`chip${contestScope === "contest" ? " selected" : ""}`}
                  aria-pressed={contestScope === "contest"}
                  onClick={() => setContestScope("contest")}
                >
                  Contest
                </button>
                <button
                  type="button"
                  className={`chip${contestScope === "allGames" ? " selected" : ""}`}
                  aria-pressed={contestScope === "allGames"}
                  onClick={() => setContestScope("allGames")}
                >
                  All Games
                </button>
              </div>
            </div>
            {contestScope === "contest" && contestTeams === null && (
              <p className="hint">
                {contestTeamsError ??
                  `No Salary File uploaded yet for ${contest} -- showing every team until one is.`}
              </p>
            )}
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
                  min={0}
                  step={0.25}
                  value={minScore}
                  onChange={(e) => setMinScore(Math.max(0, Number(e.target.value) || 0))}
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
