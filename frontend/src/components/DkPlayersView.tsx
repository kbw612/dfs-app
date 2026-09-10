import { useCallback, useEffect, useMemo, useState } from "react";
import { addDkPlayersWeek, calculateDkPlayersWeekPoints, fetchDkPlayers, fetchDkPlayersWeekStatus } from "../api";
import type { CalculateWeekPointsResult, DkPlayerRow } from "../types";
import { formatOwnershipPct, formatSalary } from "./playerDisplay";

interface DkPlayersViewProps {
  season: number;
  week: number;
  platform: string;
}

type WeekFilter = number | "all";

// Fixed 2-decimal formatting for FPTS/Non_TD_FPTS/TD_FPTS -- same
// reasoning as Contest Results' own formatPts: a column of numbers reads
// better when every row shows the same number of decimal digits.
function formatPts(value: number): string {
  return value.toFixed(2);
}

// "Add Week N Players"/"Update Week N Points" always read the All Games
// contest's Salary File/Contest Standings, regardless of whatever contest
// is currently selected in Settings -- see backend/api/dk_players/
// add_week.py's docstring for why (this tracker needs the full slate,
// which only the All Games contest is guaranteed to cover).
export function DkPlayersView({ season, week, platform }: DkPlayersViewProps) {
  const [players, setPlayers] = useState<DkPlayerRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewWeek, setViewWeek] = useState<WeekFilter>(week);

  const [addBusy, setAddBusy] = useState(false);
  const [addMessage, setAddMessage] = useState<string | null>(null);
  const [calcBusy, setCalcBusy] = useState(false);
  // The raw result (rather than pre-built strings) so each section can
  // get its own bold label and so "No stats recorded" can render as a
  // <details> the person expands only when they want to -- that list is
  // routinely hundreds of names long (most of the roster didn't play),
  // so showing it inline by default buried the actionable sections above
  // it (missing stat files, possible name mismatches).
  const [calcResult, setCalcResult] = useState<CalculateWeekPointsResult | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    return fetchDkPlayers(season, platform)
      .then((result) => setPlayers(result.players))
      .catch((err) => {
        setPlayers(null);
        setError(err instanceof Error ? err.message : "Failed to load DK Players");
      })
      .finally(() => setLoading(false));
  }, [season, platform]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Default the week-chip view to whatever week the shared Season/Week
  // control is currently pointed at, but only when THAT changes -- once
  // the person clicks a different chip, switching season/platform
  // shouldn't yank them back (they may be comparing history).
  useEffect(() => {
    setViewWeek(week);
  }, [week]);

  const availableWeeks = useMemo(() => {
    const weeks = new Set<number>(players?.map((p) => p.week) ?? []);
    weeks.add(week); // always offer a chip for the app's current week, even before it's been added
    return Array.from(weeks).sort((a, b) => a - b);
  }, [players, week]);

  const filteredPlayers = useMemo(() => {
    if (!players) return null;
    if (viewWeek === "all") return players;
    return players.filter((p) => p.week === viewWeek);
  }, [players, viewWeek]);

  async function handleAddWeek() {
    setAddBusy(true);
    setAddMessage(null);
    // Also clear the OTHER button's message -- these two actions touch
    // the same rows, so a stale "Update Week N Points" result (possible
    // name mismatches, no-stats-recorded, etc.) sitting next to a fresh
    // "Added N players" message reads as if it still applies to the just
    // -replaced rows, when it doesn't.
    setCalcResult(null);
    setCalcError(null);
    try {
      const status = await fetchDkPlayersWeekStatus(season, week, platform);
      if (status.exists) {
        const warning = status.has_calculated_points
          ? `Week ${week} already has ${status.player_count} players WITH calculated points -- replacing will lose them. Replace with the current Salary File?`
          : `Week ${week} already has ${status.player_count} players -- replace with the current Salary File?`;
        if (!window.confirm(warning)) {
          setAddBusy(false);
          return;
        }
      }
      const result = await addDkPlayersWeek(season, week, platform, status.exists);
      setAddMessage(
        `Added ${result.added_count} players for week ${result.week}${result.replaced ? " (replaced existing rows)" : ""}`
      );
      await reload();
    } catch (err) {
      setAddMessage(err instanceof Error ? err.message : "Failed to add this week's players");
    } finally {
      setAddBusy(false);
    }
  }

  async function handleCalculate() {
    setCalcBusy(true);
    setCalcResult(null);
    setCalcError(null);
    // Also clear the OTHER button's message -- see handleAddWeek's own
    // comment for why a stale message from the other action shouldn't
    // linger once a new action has run.
    setAddMessage(null);
    try {
      const result = await calculateDkPlayersWeekPoints(season, week, platform);
      setCalcResult(result);
      await reload();
    } catch (err) {
      setCalcError(err instanceof Error ? err.message : "Failed to update this week's points");
    } finally {
      setCalcBusy(false);
    }
  }

  return (
    <>
      <section className="ownership-section">
        <div className="player-pool-grid-header">
          <h2>DK Players</h2>
        </div>
        <p className="hint">
          Always uses the All Games Salary File/Contest Standings (the full slate), regardless of which contest is
          selected in Settings -- upload those under the All Games contest chip.
        </p>
        <div className="dk-players-actions">
          <div className="dk-players-button-row">
            <button type="button" className="player-pool-save-button" disabled={addBusy} onClick={handleAddWeek}>
              {addBusy ? "Adding…" : `Add Week ${week} Players`}
            </button>
            <button type="button" className="player-pool-save-button" disabled={calcBusy} onClick={handleCalculate}>
              {calcBusy ? "Updating…" : `Update Week ${week} Points`}
            </button>
          </div>
          {/* One shared, full-width message area below the button row --
              whichever action ran most recently shows its result here
              (handleAddWeek/handleCalculate each clear the OTHER's state
              first, so only one of these is ever populated at a time). */}
          {(addMessage || calcError || calcResult) && (
            <div className="dk-players-message-row">
              {addMessage && <p className="hint">{addMessage}</p>}
              {calcError && <p className="hint error">{calcError}</p>}
              {calcResult && (
                <div className="dk-players-calc-message">
                  <p className="hint">
                    <strong>Updated:</strong> {calcResult.updated_count} players for week {calcResult.week}
                  </p>
                  {calcResult.missing_stat_files.length > 0 && (
                    <p className="hint">
                      <strong>Missing stat files:</strong> {calcResult.missing_stat_files.join(", ")} -- upload them
                      in Settings
                    </p>
                  )}
                  {/* Split so a real alias problem (a close-spelling candidate exists
                      in the stat file) doesn't get buried among players who simply
                      didn't record a stat line that week -- see
                      backend/schemas/dk_players/dk_players.py's CalculateWeekPointsResult. */}
                  {calcResult.possible_stat_name_mismatches.length > 0 && (
                    <p className="hint">
                      <strong>Possible name mismatches</strong> (add a Name Alias in Settings):{" "}
                      {calcResult.possible_stat_name_mismatches
                        .map((m) => `${m.tracker_name} → ${m.suggested_match}`)
                        .join(", ")}
                    </p>
                  )}
                  {/* Collapsed by default -- this list is routinely hundreds of
                      names long (most of the roster simply didn't play), so
                      showing it inline would bury the actionable sections above. */}
                  {calcResult.no_stats_recorded.length > 0 && (
                    <details className="dk-players-collapsible">
                      <summary className="hint">
                        <strong>No stats recorded this week</strong> (likely didn't play) --{" "}
                        {calcResult.no_stats_recorded.length} players
                      </summary>
                      <p className="hint">{calcResult.no_stats_recorded.join(", ")}</p>
                    </details>
                  )}
                  {calcResult.unmatched_contest_players.length > 0 && (
                    <details className="dk-players-collapsible">
                      <summary className="hint">
                        <strong>No contest-standings match</strong> --{" "}
                        {calcResult.unmatched_contest_players.length} players
                      </summary>
                      <p className="hint">{calcResult.unmatched_contest_players.join(", ")}</p>
                    </details>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="filters">
          <div className="chip-filter">
            <span className="filter-label">Week</span>
            <div className="chip-row">
              <button
                type="button"
                className={`chip${viewWeek === "all" ? " selected" : ""}`}
                aria-pressed={viewWeek === "all"}
                onClick={() => setViewWeek("all")}
              >
                All
              </button>
              {availableWeeks.map((w) => (
                <button
                  key={w}
                  type="button"
                  className={`chip${viewWeek === w ? " selected" : ""}`}
                  aria-pressed={viewWeek === w}
                  onClick={() => setViewWeek(w)}
                >
                  {w}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && <p className="error">{error}</p>}

      {!loading && !error && filteredPlayers && (
        <section className="ownership-section">
          {filteredPlayers.length === 0 ? (
            <p className="hint">No players in the tracker yet for this week.</p>
          ) : (
            <div className="player-pool-grid-wrap">
              <table className="player-pool-grid">
                <thead>
                  <tr>
                    <th>Week</th>
                    <th className="player-pool-grid-sticky">Name</th>
                    <th>Position</th>
                    <th>Roster Position</th>
                    <th>Team</th>
                    <th>Salary</th>
                    <th>% Drafted</th>
                    <th>FPTS</th>
                    <th>Non_TD_FPTS</th>
                    <th>TD_FPTS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPlayers.map((p, i) => (
                    <tr key={i}>
                      <td>{p.week}</td>
                      <td className="player-pool-grid-sticky">{p.name}</td>
                      <td>{p.position}</td>
                      <td>{p.roster_position}</td>
                      <td>{p.team}</td>
                      <td className="player-pool-grid-num">{formatSalary(p.salary)}</td>
                      <td className="player-pool-grid-num">{formatOwnershipPct(p.pct_drafted)}</td>
                      <td className="player-pool-grid-num">{formatPts(p.fpts)}</td>
                      <td className="player-pool-grid-num">{formatPts(p.non_td_fpts)}</td>
                      <td className="player-pool-grid-num">{formatPts(p.td_fpts)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  );
}
