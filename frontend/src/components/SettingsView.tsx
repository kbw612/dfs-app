import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchDkSalaryFileInfo,
  fetchOwnershipProjectionsFileInfo,
  fetchPlayerPool,
  savePlayerAttributeEntry,
} from "../api";
import type { PlayerPoolPlayer, PlayerPoolResult } from "../types";
import { DkSalaryUpload } from "./DkSalaryUpload";
import { FileUploadStatus } from "./FileUploadStatus";
import { OwnershipProjectionsUpload } from "./OwnershipProjectionsUpload";
import { PlayerSelectionGrid } from "./PlayerSelectionGrid";

// Volume/Talent aren't scored for DST (see backend/services/player_pool/
// engine.py's _fields_for_position) -- the defaults panel only makes
// sense for the positions that actually carry these two fields.
function appliesToDefaults(position: string): boolean {
  return position !== "DST";
}

const AUTOSAVE_DEBOUNCE_MS = 800;

type AttributeField = "volume" | "talent";
type EditValues = Partial<Record<AttributeField, string>>;

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

// Only "DraftKings" has a real file format behind it today (see
// backend/services/platform_settings/prefix.py) -- a single chip, always
// selected, ready for a second option once one's actually supported.
// Same story for "Classic Main", which has no functional effect anywhere
// yet (see backend/schemas/platform_settings/platform_settings.py).
const PLATFORM_OPTIONS = ["DraftKings"] as const;
const CONTEST_OPTIONS = ["Classic Main"] as const;

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
  const [ownershipRefresh, setOwnershipRefresh] = useState(0);

  const [data, setData] = useState<PlayerPoolResult | null>(null);
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
    fetchPlayerPool(season, week, platform)
      .then((result) => {
        setData(result);
        setEditValues((prev) => {
          const next = { ...prev };
          for (const row of result.players) {
            if (!(row.player in next)) {
              next[row.player] = {
                volume: scoreToInputValue(row.volume),
                talent: scoreToInputValue(row.talent),
              };
            }
          }
          return next;
        });
      })
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load players");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform]);

  useEffect(() => {
    setEditValues({});
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, week, platform]);

  function handleDkSalaryUploaded() {
    setDkSalaryRefresh((n) => n + 1);
    load();
  }

  async function saveRow(key: string) {
    const values = editValuesRef.current[key];
    if (!values) return;
    setSavingKeys((prev) => new Set(prev).add(key));
    try {
      await savePlayerAttributeEntry({
        season,
        week,
        player: key,
        volume: inputValueToScore(values.volume),
        talent: inputValueToScore(values.talent),
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

  function updateCell(key: string, field: AttributeField, value: string) {
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

  const isNotFound = error !== null && error.includes("No DK salary file uploaded yet");
  const defaultPlayers: PlayerPoolPlayer[] = (data?.players ?? [])
    .filter((p) => appliesToDefaults(p.position))
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
        <h2>Ownership file</h2>
        <OwnershipProjectionsUpload
          season={season}
          week={week}
          platform={platform}
          onUploaded={() => setOwnershipRefresh((n) => n + 1)}
        />
        <FileUploadStatus
          season={season}
          week={week}
          platform={platform}
          fetchInfo={fetchOwnershipProjectionsFileInfo}
          refreshToken={ownershipRefresh}
        />
      </section>

      <section className="ownership-section settings-panel">
        <h2>Salary File</h2>
        <DkSalaryUpload season={season} week={week} platform={platform} onUploaded={handleDkSalaryUploaded} />
        <FileUploadStatus
          season={season}
          week={week}
          platform={platform}
          fetchInfo={fetchDkSalaryFileInfo}
          refreshToken={dkSalaryRefresh}
        />
      </section>

      <section className="ownership-section settings-panel">
        <h2>Player pool</h2>
        <p className="hint">
          Narrow down which QB/RB/WR/TE players from this week's salary file show up in Player Pool and Salary
          Blocks -- uncheck anyone you don't want to see there. DST isn't affected; every DST always shows up.
        </p>
        <PlayerSelectionGrid season={season} week={week} platform={platform} refreshToken={dkSalaryRefresh} />
      </section>

      <section className="ownership-section settings-panel">
        <div className="player-pool-grid-header">
          <h2>Player Volume/Talent defaults</h2>
          {defaultPlayers.length > 0 && <span className="player-pool-save-status">{saveStatus}</span>}
        </div>
        <p className="hint">
          These are the same Volume/Opportunities and Talent/Explosiveness values shown in the Player Pool tab -- set a
          baseline here, or override any player for just this week from Player Pool.
        </p>

        {loading && <p className="hint">Loading…</p>}
        {!loading && error && isNotFound && (
          <p className="hint">No DK salary file uploaded yet for season {season} week {week} -- upload it above.</p>
        )}
        {!loading && error && !isNotFound && <p className="error">{error}</p>}

        {!loading && !error && defaultPlayers.length > 0 && (
          <div className="player-pool-grid-wrap">
            <table className="player-pool-grid">
              <thead>
                <tr>
                  <th className="player-pool-grid-sticky">Name</th>
                  <th>Position</th>
                  <th>Team</th>
                  <th>Volume</th>
                  <th>Talent</th>
                </tr>
              </thead>
              <tbody>
                {defaultPlayers.map((row) => {
                  const key = row.player;
                  const values = editValues[key] ?? {};
                  return (
                    <tr key={key} className={dirtyKeys.has(key) ? "player-pool-row-dirty" : undefined}>
                      <td className="player-pool-grid-sticky">{row.player}</td>
                      <td>{row.position}</td>
                      <td>{row.team}</td>
                      {(["volume", "talent"] as AttributeField[]).map((field) => (
                        <td key={field}>
                          <input
                            type="number"
                            min={1}
                            max={3}
                            step="0.25"
                            title="Carries forward until changed"
                            value={values[field] ?? ""}
                            onChange={(e) => updateCell(key, field, e.target.value)}
                            onBlur={() => handleCellBlur(key)}
                          />
                        </td>
                      ))}
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
