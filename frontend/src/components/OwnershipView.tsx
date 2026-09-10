import { useEffect, useState } from "react";
import { fetchOwnershipLatest } from "../api";
import type {
  GameLeverageGroup,
  LeverageReason,
  MultiLeveragePlayer,
  OwnershipLatestResult,
  PivotGroup,
} from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { HeaderInfoPopover } from "./HeaderInfoPopover";
import {
  formatOwnershipPct,
  formatSalary,
  opponentLabel,
  PlayerNameCell,
  PlayerRow,
  playerMatchesFilters,
  roleLabel,
} from "./playerDisplay";

// LeverageReason/MultiLeveragePlayer (imported from ../types) are computed
// server-side -- see engine.py's compute_multi_leverage() -- and arrive on
// data.multi_leverage already sorted (reason count descending, salary
// descending within a tie), so the frontend just renders the list as-is:
// one dense row per player (name/salary/reason-count badge, no card
// border/padding) with no "leverage for N players" group headings --
// the badge carries that info inline instead. Reasons themselves aren't
// shown in a modal; clicking a row expands them in place, same
// click-to-expand pattern as the Pivots/Game Leverage sections.
// Salary Pivots' own formula (see backend/services/ownership/engine.py's
// compute_pivots(), DEFAULT_SALARY_TOLERANCE=$500 / DEFAULT_OWNERSHIP_GAP=
// 10.0) -- shown via HeaderInfoPopover next to that section's heading so
// the definition lives right where the section is, rather than requiring
// a trip to the backend to look it up.
const SALARY_PIVOT_NOTES: string[] = [
  "For every player (the \"trigger\"), finds every other player at the same position priced within $500 of them.",
  "A same-position player counts as a pivot if it's owned at least 10 percentage points less than the trigger.",
  "In short: a same-position, similar-salary, meaningfully-less-owned fade -- comparable price for meaningfully less ownership.",
];

function describeReason(reason: LeverageReason): string {
  const a = reason.against;
  if (reason.kind === "pivot") {
    return `Pivot for ${a.player} ${roleLabel(a)} — ${formatOwnershipPct(a.ownership_pct)} owned, ${formatSalary(a.salary)}`;
  }
  // team/opponent are only null for kind "pivot" (see LeverageReason in
  // types.ts) -- always set by the backend for kind "game".
  return `Game leverage vs ${a.player} ${roleLabel(a)} (${formatOwnershipPct(a.ownership_pct)} owned) — ${reason.team ?? "?"} vs ${reason.opponent ?? "?"}`;
}

// season/week/platform come from the shared header control / Settings
// panel (see App.tsx), same as Ownership Summary -- platform picks which
// uploaded Ownership file gets read (see backend/api/ownership/latest.py).
interface OwnershipViewProps {
  season: number;
  week: number;
  platform: string;
}

export function OwnershipView({ season, week, platform }: OwnershipViewProps) {
  const [data, setData] = useState<OwnershipLatestResult | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [fetchLoading, setFetchLoading] = useState(false);

  const [teamFilter, setTeamFilter] = useState<Set<string>>(new Set());
  const [positionFilter, setPositionFilter] = useState<Set<string>>(new Set());
  // Keyed by trigger player name (Pivots section), "team-opponent" (Game
  // Leverage -- one row per game, collapsed by default), or the leverage
  // player's own name (Leverage & pivot plays) -- same interaction pattern
  // throughout, click the row (or its arrow) to expand.
  const [expandedPivots, setExpandedPivots] = useState<Set<string>>(new Set());
  const [expandedGames, setExpandedGames] = useState<Set<string>>(new Set());
  const [expandedMultiLeverage, setExpandedMultiLeverage] = useState<Set<string>>(new Set());

  function makeToggle(setter: (updater: (prev: Set<string>) => Set<string>) => void) {
    return (key: string) => {
      setter((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
        }
        return next;
      });
    };
  }

  const togglePivot = makeToggle(setExpandedPivots);
  const toggleGame = makeToggle(setExpandedGames);
  const toggleMultiLeverage = makeToggle(setExpandedMultiLeverage);

  // Reads whatever's currently uploaded via Settings' Ownership file --
  // same source and same "no separate load step" behavior as Ownership
  // Summary -- so a season/week/platform change here just refetches, the
  // same way switching tabs would.
  useEffect(() => {
    setFetchLoading(true);
    setFetchError(null);
    fetchOwnershipLatest(season, week, platform)
      .then((result) => setData(result))
      .catch((err) => {
        setData(null);
        // The 404 detail from GET /latest ("No ownership projections file
        // uploaded yet...") isn't a real error -- it's the expected state
        // before anyone's used Settings' Ownership file upload yet.
        setFetchError(err instanceof Error ? err.message : "Failed to load ownership data");
      })
      .finally(() => setFetchLoading(false));
  }, [season, week, platform]);

  const isNotFound = fetchError !== null && fetchError.includes("No ownership projections file uploaded yet");

  const teamOptions = data ? [...new Set(data.players.map((p) => p.team))].sort() : [];
  const positionOptions = data ? [...new Set(data.players.map((p) => p.position))].sort() : [];

  const filteredHighOwned = data?.high_owned.filter((p) => playerMatchesFilters(p, teamFilter, positionFilter)) ?? [];

  const filteredGameLeverage: GameLeverageGroup[] =
    data?.game_leverage
      .map((g) => ({
        ...g,
        chalk_players: g.chalk_players.filter((p) => playerMatchesFilters(p, teamFilter, positionFilter)),
        pivot_candidates: g.pivot_candidates.filter((p) => playerMatchesFilters(p, teamFilter, positionFilter)),
      }))
      .filter((g) => g.chalk_players.length > 0 || g.pivot_candidates.length > 0) ?? [];

  const filteredPivots: PivotGroup[] =
    data?.pivots.filter((group) => playerMatchesFilters(group.trigger, teamFilter, positionFilter)) ?? [];

  // Already sorted by the backend (reason count desc, salary desc within a
  // tie) -- no client-side grouping or re-sorting needed, just filtering.
  const filteredMultiLeverage: MultiLeveragePlayer[] =
    data?.multi_leverage.filter((entry) => playerMatchesFilters(entry.player, teamFilter, positionFilter)) ?? [];

  return (
    <>
      {fetchLoading && <p className="hint">Loading…</p>}

      {!fetchLoading && fetchError && isNotFound && (
        <p className="hint">
          No ownership file uploaded yet for season {season} week {week} -- upload it in the Settings tab.
        </p>
      )}
      {!fetchLoading && fetchError && !isNotFound && <p className="error">{fetchError}</p>}

      {!fetchLoading && data && (
        <>
          <p className="hint">
            Week {data.week}, {data.season} · {data.players.length} players · leverage point {data.leverage_point}%
            ownership · last uploaded {new Date(data.uploaded_at).toLocaleString()}
          </p>

          <div className="filters">
            <ChipMultiSelect label="Filter by team" options={teamOptions} selected={teamFilter} onChange={setTeamFilter} />
            <ChipMultiSelect
              label="Filter by position"
              options={positionOptions}
              selected={positionFilter}
              onChange={setPositionFilter}
            />
          </div>

          <section className="ownership-section">
            <h2 className="ownership-pivot-players-heading">
              Players who are game or salary pivots against 2 or more other players
            </h2>
            {filteredMultiLeverage.length === 0 ? (
              <p className="hint">No players currently qualify under the current filters.</p>
            ) : (
              <ul className="ownership-player-list pivot-card-list">
                {filteredMultiLeverage.map((entry, index) => {
                  const key = entry.player.player;
                  const open = expandedMultiLeverage.has(key);
                  // Already sorted by reason count descending -- a plain
                  // divider (no text heading, per the "no group headings"
                  // decision) marks where the count drops from one row to
                  // the next, e.g. the ×3 rows to the ×2 rows.
                  const isNewCountGroup = index > 0 && filteredMultiLeverage[index - 1].reasons.length !== entry.reasons.length;
                  return (
                    <li key={key} className={isNewCountGroup ? "ownership-leverage-group-divider" : undefined}>
                      <div
                        className="ownership-player-row ownership-multi-leverage-row"
                        role="button"
                        tabIndex={0}
                        aria-expanded={open}
                        onClick={() => toggleMultiLeverage(key)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleMultiLeverage(key);
                          }
                        }}
                      >
                        <PlayerNameCell player={entry.player.player} role={roleLabel(entry.player)} bubbleClick />
                        <span className="ownership-player-salary">{formatSalary(entry.player.salary)}</span>
                        <span className="ownership-player-pct">{formatOwnershipPct(entry.player.ownership_pct)}</span>
                        <span className="ownership-leverage-badge">×{entry.reasons.length}</span>
                      </div>
                      {open && (
                        <ul className="ownership-leverage-reasons">
                          {entry.reasons.map((reason, i) => (
                            <li key={i} className="ownership-leverage-reason">
                              {describeReason(reason)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="ownership-section">
            <h2>Chalk (high-owned)</h2>
            {filteredHighOwned.length === 0 ? (
              <p className="hint">No high-owned players match the current filters.</p>
            ) : (
              <ul className="ownership-player-list pivot-card-list">
                {filteredHighOwned.map((p) => (
                  <PlayerRow key={p.player} p={p} />
                ))}
              </ul>
            )}
          </section>

          <section className="ownership-section">
            <h2>Game Pivots</h2>
            {filteredGameLeverage.length === 0 ? (
              <p className="hint">No games with chalk or pivot candidates match the current filters.</p>
            ) : (
              <ul className="ownership-game-list">
                {filteredGameLeverage.map((g) => {
                  const gameKey = `${g.team}-${g.opponent}`;
                  const open = expandedGames.has(gameKey);
                  const pivotCount = g.pivot_candidates.length;
                  return (
                    <li key={gameKey}>
                      <div
                        className="ownership-game-summary"
                        role="button"
                        tabIndex={0}
                        aria-expanded={open}
                        onClick={() => toggleGame(gameKey)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleGame(gameKey);
                          }
                        }}
                      >
                        <span className="ownership-game-matchup">
                          {g.team} vs {g.opponent}
                        </span>
                        <span className="ownership-game-counts">
                          {g.chalk_players.length} chalk · {pivotCount} pivot{pivotCount === 1 ? "" : "s"}{" "}
                          {open ? "▴" : "▾"}
                        </span>
                      </div>
                      {open && (
                        <div className="ownership-game-detail">
                          {g.chalk_players.length > 0 && (
                            <div className="ownership-game-subgroup">
                              <h4>Chalk</h4>
                              <ul className="ownership-player-list">
                                {g.chalk_players.map((p) => (
                                  <PlayerRow key={p.player} p={p} />
                                ))}
                              </ul>
                            </div>
                          )}
                          {pivotCount > 0 && (
                            <div className="ownership-game-subgroup">
                              <h4>Pivots</h4>
                              <ul className="ownership-player-list">
                                {g.pivot_candidates.map((p) => (
                                  <PlayerRow key={p.player} p={p} />
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="ownership-section">
            <h2>
              Salary Pivots
              <HeaderInfoPopover lines={SALARY_PIVOT_NOTES} ariaLabel="Salary pivot formula" />
            </h2>
            {filteredPivots.length === 0 ? (
              <p className="hint">No pivot groups match the current filters.</p>
            ) : (
              <ul className="ownership-pivot-groups pivot-card-list">
                {filteredPivots.map((group) => {
                  const key = group.trigger.player;
                  const open = expandedPivots.has(key);
                  return (
                    <li key={key} className="ownership-pivot-group">
                      <div
                        className="ownership-pivot-summary"
                        role="button"
                        tabIndex={0}
                        aria-expanded={open}
                        onClick={() => togglePivot(key)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            togglePivot(key);
                          }
                        }}
                      >
                        <div className="ownership-pivot-header">
                          <PlayerNameCell player={group.trigger.player} role={roleLabel(group.trigger)} bubbleClick />
                          <span className="ownership-player-pct">{formatOwnershipPct(group.trigger.ownership_pct)}</span>
                        </div>
                        <div className="ownership-pivot-meta">
                          {opponentLabel(group.trigger)} · {formatSalary(group.trigger.salary)} · {group.pivots.length}{" "}
                          pivot{group.pivots.length === 1 ? "" : "s"} {open ? "▴" : "▾"}
                        </div>
                      </div>
                      {open && (
                        <ul className="ownership-player-list ownership-pivot-list">
                          {group.pivots.map((p) => (
                            <PlayerRow key={p.player} p={p} />
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </>
      )}
    </>
  );
}
