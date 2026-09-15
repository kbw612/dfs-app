import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchContestStandingsFileInfo,
  fetchDepthChartRoster,
  fetchDkSalaryFileInfo,
  fetchPlayerDefaults,
  fetchSalaryMultiplier,
  savePlayerDefaultEntry,
  saveSalaryMultiplierEntry,
} from "../api";
import type { DepthChartRosterPlayer, PlayerDefaultEntryInput } from "../types";
import { DFS_TYPE_OPTIONS } from "../dfsTypes";
import { ContestStandingsUpload } from "./ContestStandingsUpload";
import { DkSalaryUpload } from "./DkSalaryUpload";
import { FileUploadStatus } from "./FileUploadStatus";
import { HeaderInfoPopover } from "./HeaderInfoPopover";
import { NameAliasesPanel } from "./NameAliasesPanel";
import { OwnershipFileStatus } from "./OwnershipFileStatus";
import { OwnershipProjectionsUpload } from "./OwnershipProjectionsUpload";
import { PlayerSelectionGrid } from "./PlayerSelectionGrid";
import { ScheduleUpload } from "./ScheduleUpload";
import { TALENT_EXPLOSIVENESS_NOTES, VOLUME_OPPORTUNITIES_NOTES } from "./scoringNotes";
import { WeeklyStatsFileStatusList, WeeklyStatsUpload } from "./WeeklyStatsUpload";

// Mirrors Player Pool's own position filter chips (see PlayerPoolView.tsx's
// POSITIONS) -- DST is left out since Volume/Talent/DFS Type don't apply
// to it (see backend/services/player_pool/engine.py's
// _fields_for_position); the roster endpoint this grid reads from already
// only ever returns QB/RB/WR/TE, so there's nothing to filter out here.
const DEFAULTS_POSITIONS = ["QB", "RB", "WR", "TE"] as const;
type DefaultsPosition = (typeof DEFAULTS_POSITIONS)[number];

// Scoped to this grid only -- narrows Player Default Factors down to
// *only* each position's top depth-chart slots (QB1-2, RB1-3, WR1-4,
// TE1-3), since backups rarely need a hand-set Volume/Talent baseline.
// Player Rankings and Salary Blocks are unaffected -- they're already
// narrowed by the Player pool selection grid above this one.
const DEPTH_CUTOFF_BY_POSITION: Record<DefaultsPosition, number> = {
  QB: 2,
  RB: 3,
  WR: 4,
  TE: 3,
};

function withinDepthCutoff(row: DepthChartRosterPlayer): boolean {
  const cutoff = DEPTH_CUTOFF_BY_POSITION[row.position as DefaultsPosition];
  return cutoff === undefined ? false : row.depth_rank <= cutoff;
}

const AUTOSAVE_DEBOUNCE_MS = 800;

function multiplierToInputValue(value: number | null): string {
  return value === null ? "" : String(value);
}

// Blank means "use the computed default" -- saved as a real null override,
// not a literal number, so clearing the input reverts to the default
// rather than freezing in whatever it last resolved to.
function inputValueToMultiplier(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

type AttributeField = "volume" | "talent";
type DefaultsField = AttributeField | "dfs_type";
type EditValues = Partial<Record<DefaultsField, string>>;

function scoreToInputValue(value: number | null): string {
  return value === null ? "" : String(value);
}

function inputValueToScore(value: string | undefined): number | null {
  if (value === undefined) return null;
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

// "None" is a UI-only sentinel for the dropdown (see dfsTypes.ts) --
// saved as a real null, not the literal string "None".
function dfsTypeToInputValue(value: string | null): string {
  return value ?? "None";
}

function inputValueToDfsType(value: string | undefined): string | null {
  return value === undefined || value === "None" ? null : value;
}

// Only "DraftKings" has a real file format behind it today (see
// backend/services/platform_settings/prefix.py) -- a single chip, always
// selected, ready for a second option once one's actually supported.
// "Classic Main" and "All Games" each resolve to their own independent
// Salary File/Contest Standings file -- see backend/services/
// platform_settings/prefix.py's contest_slug() and
// backend/repositories/dk_salary/salary_snapshot_repo.py /
// backend/repositories/contest_results/contest_standings_repo.py for the
// exact filenames each one maps to.
const PLATFORM_OPTIONS = ["DraftKings"] as const;
const CONTEST_OPTIONS = ["Classic Main", "All Games"] as const;

interface SettingsViewProps {
  season: number;
  week: number;
  onSeasonChange: (season: number) => void;
  onWeekChange: (week: number) => void;
  platform: string;
  contest: string;
  onPlatformChange: (platform: string) => void;
  onContestChange: (contest: string) => void;
}

export function SettingsView({
  season,
  week,
  onSeasonChange,
  onWeekChange,
  platform,
  contest,
  onPlatformChange,
  onContestChange,
}: SettingsViewProps) {
  const [dkSalaryRefresh, setDkSalaryRefresh] = useState(0);
  const [scheduleRefresh, setScheduleRefresh] = useState(0);
  const [contestStandingsRefresh, setContestStandingsRefresh] = useState(0);
  const [weeklyStatsRefresh, setWeeklyStatsRefresh] = useState(0);
  const [ownershipRefresh, setOwnershipRefresh] = useState(0);
  const [defaultsPosition, setDefaultsPosition] = useState<DefaultsPosition>("QB");

  // Salary Multiplier -- scoped to `platform` alone, no season/week (see
  // backend/schemas/salary_multiplier/salary_multiplier.py).
  // multiplierInput is the raw text of the override input, seeded from the
  // saved override only (blank when there isn't one); multiplierResolved
  // is the actual value in effect (override or computed default), used
  // just to show the current default as a hint next to the input.
  const [multiplierInput, setMultiplierInput] = useState("");
  const [multiplierResolved, setMultiplierResolved] = useState<number | null>(null);
  const [multiplierSaving, setMultiplierSaving] = useState(false);
  const [multiplierError, setMultiplierError] = useState<string | null>(null);
  const multiplierDebounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // The full, all-32-teams offense roster from the latest depth-chart
  // scrape -- independent of season/week/platform (see
  // fetchDepthChartRoster), unlike the rest of Settings. null until the
  // first fetch resolves, [] if it resolved but found no depth-chart
  // snapshot at all yet.
  const [roster, setRoster] = useState<DepthChartRosterPlayer[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editValues, setEditValues] = useState<Record<string, EditValues>>({});
  const [dirtyKeys, setDirtyKeys] = useState<Set<string>>(new Set());
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());

  const editValuesRef = useRef(editValues);
  useEffect(() => {
    editValuesRef.current = editValues;
  }, [editValues]);

  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  useEffect(() => {
    const timers = debounceTimers.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    // Roster comes from the depth-chart scrape, not this week's DK salary
    // file -- see fetchDepthChartRoster's own docstring for why this grid
    // needs to be independent of which teams happen to be on a given
    // week's slate. Defaults are still scoped per season, so that half
    // still depends on `season`.
    Promise.all([fetchDepthChartRoster(), fetchPlayerDefaults(season)])
      .then(([rosterResult, defaultsResult]) => {
        setRoster(rosterResult.players);
        const defaultsByPlayer: Record<string, PlayerDefaultEntryInput> = {};
        for (const entry of defaultsResult.defaults) {
          defaultsByPlayer[entry.player] = entry;
        }
        // Seeded from each player's saved Default (blank if they've never
        // had one set), not from anything week-specific -- this grid edits
        // the Default itself.
        setEditValues((prev) => {
          const next = { ...prev };
          for (const row of rosterResult.players) {
            if (!(row.player in next)) {
              const defaultEntry = defaultsByPlayer[row.player];
              next[row.player] = {
                volume: scoreToInputValue(defaultEntry?.volume ?? null),
                talent: scoreToInputValue(defaultEntry?.talent ?? null),
                dfs_type: dfsTypeToInputValue(defaultEntry?.dfs_type ?? null),
              };
            }
          }
          return next;
        });
      })
      .catch((err) => {
        setRoster(null);
        setError(err instanceof Error ? err.message : "Failed to load players");
      })
      .finally(() => setLoading(false));
  }, [season]);

  useEffect(() => {
    setEditValues({});
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season]);

  useEffect(() => {
    fetchSalaryMultiplier(platform)
      .then((result) => {
        setMultiplierResolved(result.multiplier);
        setMultiplierInput(multiplierToInputValue(result.override));
        setMultiplierError(null);
      })
      .catch((err) => {
        setMultiplierError(err instanceof Error ? err.message : "Failed to load salary multiplier");
      });
  }, [platform]);

  useEffect(() => {
    const timer = multiplierDebounceTimer;
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  async function saveMultiplier(value: string) {
    setMultiplierSaving(true);
    try {
      const result = await saveSalaryMultiplierEntry({ platform, multiplier: inputValueToMultiplier(value) });
      setMultiplierResolved(result.multiplier);
      setMultiplierError(null);
    } catch (err) {
      setMultiplierError(err instanceof Error ? err.message : "Failed to save salary multiplier");
    } finally {
      setMultiplierSaving(false);
    }
  }

  function handleMultiplierChange(value: string) {
    setMultiplierInput(value);
    if (multiplierDebounceTimer.current) clearTimeout(multiplierDebounceTimer.current);
    multiplierDebounceTimer.current = setTimeout(() => {
      multiplierDebounceTimer.current = null;
      saveMultiplier(value);
    }, AUTOSAVE_DEBOUNCE_MS);
  }

  function handleMultiplierBlur() {
    if (multiplierDebounceTimer.current) {
      clearTimeout(multiplierDebounceTimer.current);
      multiplierDebounceTimer.current = null;
    }
    saveMultiplier(multiplierInput);
  }

  function handleDkSalaryUploaded() {
    setDkSalaryRefresh((n) => n + 1);
  }

  function handleContestStandingsUploaded() {
    setContestStandingsRefresh((n) => n + 1);
  }

  async function saveRow(key: string) {
    const values = editValuesRef.current[key];
    if (!values) return;
    setSavingKeys((prev) => new Set(prev).add(key));
    try {
      // No `week` -- this saves the player's season-wide Default, not a
      // specific week's Player Pool entry (see backend/schemas/
      // player_defaults/player_defaults.py).
      await savePlayerDefaultEntry({
        season,
        player: key,
        volume: inputValueToScore(values.volume),
        talent: inputValueToScore(values.talent),
        dfs_type: inputValueToDfsType(values.dfs_type),
      });
      setDirtyKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save player defaults");
    } finally {
      setSavingKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }

  function scheduleAutosave(key: string) {
    if (debounceTimers.current[key]) clearTimeout(debounceTimers.current[key]);
    debounceTimers.current[key] = setTimeout(() => {
      delete debounceTimers.current[key];
      saveRow(key);
    }, AUTOSAVE_DEBOUNCE_MS);
  }

  function updateCell(key: string, field: DefaultsField, value: string) {
    setEditValues((prev) => ({ ...prev, [key]: { ...prev[key], [field]: value } }));
    setDirtyKeys((prev) => new Set(prev).add(key));
    scheduleAutosave(key);
  }

  function handleCellBlur(key: string) {
    if (debounceTimers.current[key]) {
      clearTimeout(debounceTimers.current[key]);
      delete debounceTimers.current[key];
    }
    saveRow(key);
  }

  const rosterIsEmpty = roster !== null && roster.length === 0;
  const defaultPlayers: DepthChartRosterPlayer[] = (roster ?? [])
    .filter((p) => p.position === defaultsPosition && withinDepthCutoff(p))
    .sort((a, b) => a.player.localeCompare(b.player));
  const saveStatus = savingKeys.size > 0 ? "Saving…" : dirtyKeys.size > 0 ? "Unsaved changes" : "All changes saved";

  return (
    <>
      <section className="ownership-section settings-panel">
        <h2>Platform &amp; contest</h2>
        <div className="chip-filter">
          <span className="filter-label">Platform</span>
          <div className="chip-row">
            {PLATFORM_OPTIONS.map((p) => (
              <button
                key={p}
                type="button"
                className={`chip${platform === p ? " selected" : ""}`}
                aria-pressed={platform === p}
                onClick={() => onPlatformChange(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
        <div className="chip-filter">
          <span className="filter-label">Contest</span>
          <div className="chip-row">
            {CONTEST_OPTIONS.map((c) => (
              <button
                key={c}
                type="button"
                className={`chip${contest === c ? " selected" : ""}`}
                aria-pressed={contest === c}
                onClick={() => onContestChange(c)}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="ownership-section settings-panel">
        <h2>Salary Multiplier</h2>
        <p className="hint">
          Used to compute Player Rankings' Expected FPTS column (salary &times; multiplier / 1000). Scoped to{" "}
          {platform} alone -- leave blank to use the default ({multiplierResolved ?? "…"}).
        </p>
        <div className="ownership-load-form">
          <label>
            Multiplier
            <input
              type="number"
              step="0.1"
              placeholder={multiplierResolved !== null ? String(multiplierResolved) : undefined}
              value={multiplierInput}
              onChange={(e) => handleMultiplierChange(e.target.value)}
              onBlur={handleMultiplierBlur}
            />
          </label>
          {multiplierSaving && <span className="player-pool-save-status">Saving…</span>}
        </div>
        {multiplierError && <p className="error">{multiplierError}</p>}
      </section>

      <section className="ownership-section settings-panel">
        <h2>Season &amp; week</h2>
        <div className="ownership-load-form">
          <label>
            Season
            <input type="number" value={season} onChange={(e) => onSeasonChange(Number(e.target.value) || season)} />
          </label>
          <label>
            Week
            <input
              type="number"
              min={1}
              max={18}
              value={week}
              onChange={(e) => onWeekChange(Number(e.target.value) || week)}
            />
          </label>
        </div>
      </section>

      <section className="ownership-section settings-panel">
        <h2>Schedule</h2>
        <p className="hint">
          Team/Week/Opponent/GameLocation for the whole season -- feeds the Game Logs tab's Opponent, GameLoc, and
          Game filter. One file per season, not tied to week/platform/contest.
        </p>
        <ScheduleUpload season={season} refreshToken={scheduleRefresh} onUploaded={() => setScheduleRefresh((n) => n + 1)} />
      </section>

      <section className="ownership-section settings-panel">
        <h2>Ownership file</h2>
        <OwnershipProjectionsUpload
          season={season}
          week={week}
          platform={platform}
          onUploaded={() => setOwnershipRefresh((n) => n + 1)}
        />
        <OwnershipFileStatus season={season} week={week} platform={platform} refreshToken={ownershipRefresh} />
      </section>

      <section className="ownership-section settings-panel">
        <h2>Salary File</h2>
        <p className="hint">
          Saved/loaded per Contest above -- {contest} uses its own independent file, so switching the Contest chip
          switches which upload every tab reads.
        </p>
        <DkSalaryUpload
          season={season}
          week={week}
          platform={platform}
          contest={contest}
          onUploaded={handleDkSalaryUploaded}
        />
        <FileUploadStatus
          season={season}
          week={week}
          platform={platform}
          contest={contest}
          fetchInfo={fetchDkSalaryFileInfo}
          refreshToken={dkSalaryRefresh}
        />
      </section>

      <section className="ownership-section settings-panel">
        <h2>Contest standings</h2>
        <p className="hint">
          The Contest Results tab's own input -- DraftKings' "Export to CSV" download from a contest you entered.
          Requires this week's Salary File above to already be uploaded, since Salary/Exp Pts there are joined in
          from it. Saved/loaded per Contest above, same as the Salary File.
        </p>
        <ContestStandingsUpload
          season={season}
          week={week}
          platform={platform}
          contest={contest}
          onUploaded={handleContestStandingsUploaded}
        />
        <FileUploadStatus
          season={season}
          week={week}
          platform={platform}
          contest={contest}
          fetchInfo={fetchContestStandingsFileInfo}
          refreshToken={contestStandingsRefresh}
        />
      </section>

      <section className="ownership-section settings-panel">
        <h2>Weekly stats</h2>
        <p className="hint">
          The DK Players tab's own input for "Update Week N Points" -- QB/RB/WR/TE stat exports scraped from
          FantasyData for last week's games. Not tied to a platform; requires that week's Contest Standings above to
          already be uploaded too, since FPTS/%Drafted there is the source of truth this gets combined with.
        </p>
        <WeeklyStatsUpload season={season} week={week} onUploaded={() => setWeeklyStatsRefresh((n) => n + 1)} />
        <WeeklyStatsFileStatusList season={season} week={week} refreshToken={weeklyStatsRefresh} />
      </section>

      <section className="ownership-section settings-panel">
        <h2>Name aliases</h2>
        <p className="hint">
          Fixes cross-file name mismatches for the DK Players tab -- e.g. the Salary File says "James Cook III" but
          FantasyData/Contest Standings say "James Cook". Add an alias here and "Update Week N Points" will match
          them up automatically.
        </p>
        <NameAliasesPanel />
      </section>

      <section className="ownership-section settings-panel">
        <h2>Player pool</h2>
        <p className="hint">
          Narrow down which QB/RB/WR/TE players from this week's salary file show up in Player Rankings and Salary
          Blocks -- uncheck anyone you don't want to see there. DST isn't affected; every DST always shows up.
        </p>
        <PlayerSelectionGrid
          season={season}
          week={week}
          platform={platform}
          contest={contest}
          refreshToken={dkSalaryRefresh}
        />
      </section>

      <section className="ownership-section settings-panel">
        <div className="player-pool-grid-header">
          <h2>Player Default Factors</h2>
          {defaultPlayers.length > 0 && <span className="player-pool-save-status">{saveStatus}</span>}
        </div>
        <p className="hint">
          Set each player's baseline Volume/Opportunities, Talent/Explosiveness, and DFS Type once here -- not tied
          to a specific week, contest, or platform. Player Rankings starts from this Default for a week that hasn't
          been explicitly scored yet (falling back to 2.0 if there's no Default either), and any edit made directly
          in Player Rankings only affects that one week. The player list itself comes straight from the latest
          depth-chart scrape (not this week's DK salary file), so it always covers all 32 teams -- limited to only
          each position's top depth-chart slots (QB1-2, RB1-3, WR1-4, TE1-3).
        </p>

        <div className="filters">
          <div className="chip-filter">
            <span className="filter-label">Position</span>
            <div className="chip-row">
              {DEFAULTS_POSITIONS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`chip${defaultsPosition === p ? " selected" : ""}`}
                  aria-pressed={defaultsPosition === p}
                  onClick={() => setDefaultsPosition(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading && <p className="hint">Loading…</p>}
        {!loading && error && <p className="error">{error}</p>}
        {!loading && !error && rosterIsEmpty && (
          <p className="hint">
            No depth-chart data yet -- retrieve depth charts (Compare Depth Charts tab) first.
          </p>
        )}

        {!loading && !error && !rosterIsEmpty && defaultPlayers.length === 0 && (
          <p className="hint">No {defaultsPosition} players loaded.</p>
        )}

        {!loading && !error && defaultPlayers.length > 0 && (
          <div className="player-pool-grid-wrap player-defaults-grid-wrap">
            <table className="player-pool-grid player-defaults-grid">
              <thead>
                <tr>
                  <th className="player-pool-grid-sticky player-selection-name-col">Name</th>
                  <th>Position</th>
                  <th>Team</th>
                  <th>
                    Volume/
                    <br />
                    Opportunities
                    <HeaderInfoPopover title="Volume/Opportunities" lines={VOLUME_OPPORTUNITIES_NOTES} />
                  </th>
                  <th>
                    Talent/
                    <br />
                    Explosiveness
                    <HeaderInfoPopover title="Talent/Explosiveness" lines={TALENT_EXPLOSIVENESS_NOTES} />
                  </th>
                  <th>DFS Type</th>
                </tr>
              </thead>
              <tbody>
                {defaultPlayers.map((row) => {
                  const key = row.player;
                  const values = editValues[key] ?? {};
                  return (
                    <tr key={key} className={dirtyKeys.has(key) ? "player-pool-row-dirty" : undefined}>
                      <td className="player-pool-grid-sticky player-selection-name-col">{row.player}</td>
                      <td>{row.position}</td>
                      <td>{row.team}</td>
                      {(["volume", "talent"] as AttributeField[]).map((field) => (
                        <td key={field}>
                          <input
                            type="number"
                            min={1}
                            max={3}
                            step="0.25"
                            title="Blank means Player Rankings falls back to 2.0 for weeks without their own entry"
                            value={values[field] ?? ""}
                            onChange={(e) => updateCell(key, field, e.target.value)}
                            onBlur={() => handleCellBlur(key)}
                          />
                        </td>
                      ))}
                      <td>
                        <select
                          value={values.dfs_type ?? "None"}
                          onChange={(e) => updateCell(key, "dfs_type", e.target.value)}
                        >
                          {DFS_TYPE_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
