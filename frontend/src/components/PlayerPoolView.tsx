import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { applyVegasLines, fetchMyPlayerPool, fetchPlayerPool, saveMyPlayerPoolEntry, savePlayerPoolEntry } from "../api";
import type { GameEnvironmentEntry, PlayerPoolPlayer, PlayerPoolResult } from "../types";
import { HeaderInfoPopover } from "./HeaderInfoPopover";
import { formatOwnershipPct, formatSalary } from "./playerDisplay";
import {
  GAME_ENVIRONMENT_NOTES,
  GAME_MATCHUP_NOTES,
  OWNERSHIP_NOTES,
  TALENT_EXPLOSIVENESS_NOTES,
  VOLUME_OPPORTUNITIES_NOTES,
} from "./scoringNotes";

// Same "alphabetically-sorted TEAM1-TEAM2" convention as
// backend/services/vegas_lines/scraper.py's _game_key and
// backend/services/player_pool/engine.py's game_id -- lets a row look up
// its own game's GameEnvironmentEntry out of PlayerPoolResult.game_environment
// (one entry per game, not per player) without the backend needing to
// duplicate that data onto every row.
function gameEnvKey(team: string, opponent: string): string {
  return [team, opponent].sort().join("-");
}

// Lines for the per-row "Vegas line" popover next to the Game Environment
// input -- the actual numbers driving that row's suggested score, so a
// person second-guessing the suggestion doesn't have to flip to the Vegas
// Lines tab to see why. No entry yet (odds not applied for this game) gets
// a single explanatory line instead of blank.
function vegasLineNotes(entry: GameEnvironmentEntry | undefined): string[] {
  if (!entry) {
    return ["No Vegas Lines applied yet for this game -- see the Vegas Lines tab."];
  }
  const away = entry.away_implied_total === null ? "-" : entry.away_implied_total;
  const home = entry.home_implied_total === null ? "-" : entry.home_implied_total;
  const ou = entry.over_under === null ? "-" : entry.over_under;
  return [`${entry.away_team} (${away}) at ${entry.home_team} (${home})`, `Over/Under ${ou}`];
}

type ScoreFieldKey = "game_environment" | "game_matchup" | "ownership" | "volume" | "talent" | "salary_value";

interface ScoreFieldConfig {
  key: ScoreFieldKey;
  label: string;
}

// QBs/RBs/WRs/TEs share the same 5 rules; DSTs use their own 2 (see the
// plan discussion -- there's no "ownership"/"talent" concept for a
// defense, just Game Matchup + how attractively priced it is this week).
// Column sets differ by position, so the grid shows exactly one
// position's columns at a time rather than a combined "All" view.
const OFFENSE_SCORE_FIELDS: ScoreFieldConfig[] = [
  { key: "game_environment", label: "Game Environment" },
  { key: "game_matchup", label: "Matchup" },
  { key: "ownership", label: "Ownership" },
  { key: "volume", label: "Volume/Opportunities" },
  { key: "talent", label: "Talent/Explosiveness" },
];

const DST_SCORE_FIELDS: ScoreFieldConfig[] = [
  { key: "game_matchup", label: "Matchup" },
  { key: "salary_value", label: "Salary value" },
];

function scoreFieldsForPosition(position: string): ScoreFieldConfig[] {
  return position === "DST" ? DST_SCORE_FIELDS : OFFENSE_SCORE_FIELDS;
}

// Fields that fall back to that player's Settings Default (Player Default
// Settings grid) when left blank for this week, rather than to a flat
// neutral value -- see backend/schemas/player_defaults/player_defaults.py.
// No carry-forward from an earlier week anymore -- every week is
// independent.
const DEFAULT_FALLBACK_FIELDS = new Set<ScoreFieldKey>(["volume", "talent"]);

const POSITIONS = ["QB", "RB", "WR", "TE", "DST"] as const;
type Position = (typeof POSITIONS)[number];

const AUTOSAVE_DEBOUNCE_MS = 800;

function formatTotal(total: number): string {
  return total % 1 === 0 ? String(total) : total.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

// Same trimming as formatTotal -- expected_fpts is a plain fantasy-points
// number, not currency, so no $ sign (per the user's own worked examples:
// salary 5000 -> 20, salary 9000 -> 36).
function formatExpectedFpts(value: number): string {
  return formatTotal(value);
}

// The resolved Salary Multiplier isn't returned as its own field on
// PlayerPoolResult -- it's baked into every row's expected_fpts already
// (see backend/services/player_pool/engine.py). Back it out from any one
// row with a real salary so the "Expected FPTS (Nx)" header always
// reflects whatever multiplier is actually in effect for this platform,
// without a second API call.
function resolvedMultiplierLabel(players: PlayerPoolPlayer[]): string {
  const withSalary = players.find((p) => p.salary > 0);
  if (!withSalary) return "…";
  const multiplier = withSalary.expected_fpts / (withSalary.salary / 1000);
  return formatTotal(multiplier);
}

// Edit-form values are kept as strings (not numbers) so an input can sit
// empty mid-edit rather than snapping to 0 -- parsed back to number|null
// only when saving/totaling.
type EditValues = Partial<Record<ScoreFieldKey, string>>;

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

function playerKey(p: PlayerPoolPlayer): string {
  return p.player;
}

// Seeded from the raw override, not the blended row.game_environment --
// leaving the Game Environment cell blank and saving should mean "keep
// using the formula's suggestion," not "freeze in whatever it happened
// to suggest right now" (see types.ts's PlayerPoolPlayer docstring).
function buildEditValues(row: PlayerPoolPlayer): EditValues {
  return {
    game_environment: scoreToInputValue(row.game_environment_override),
    game_matchup: scoreToInputValue(row.game_matchup),
    ownership: scoreToInputValue(row.ownership),
    volume: scoreToInputValue(row.volume),
    talent: scoreToInputValue(row.talent),
    salary_value: scoreToInputValue(row.salary_value),
  };
}

// season/week come from the shared header control (see App.tsx) rather
// than being owned here. platform comes from the shared Settings panel
// (see App.tsx) -- it picks which platform's raw salary file gets loaded
// (see backend/api/player_pool/latest.py).
interface PlayerPoolViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

export function PlayerPoolView({ season, week, platform, contest }: PlayerPoolViewProps) {
  const [data, setData] = useState<PlayerPoolResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [position, setPosition] = useState<Position>("QB");
  const [editValues, setEditValues] = useState<Record<string, EditValues>>({});
  const [dirtyKeys, setDirtyKeys] = useState<Set<string>>(new Set());
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());
  const [gameEnvUpdating, setGameEnvScraping] = useState(false);
  const [gameEnvUpdateMessage, setGameEnvScrapeMessage] = useState<string | null>(null);

  // Which players are currently in My Player Pool for this (season, week,
  // platform) -- drives the checkbox column below. Loaded separately from
  // the main player-pool fetch (its own tab, own endpoint) so a failure
  // there doesn't block this grid from loading.
  const [myPoolMembers, setMyPoolMembers] = useState<Set<string>>(new Set());
  const [myPoolSavingKeys, setMyPoolSavingKeys] = useState<Set<string>>(new Set());

  const editValuesRef = useRef(editValues);
  useEffect(() => {
    editValuesRef.current = editValues;
  }, [editValues]);

  const seededWeekKeyRef = useRef<string | null>(null);
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

    fetchPlayerPool(season, week, platform, contest)
      .then((result) => {
        setData(result);
        const weekKey = `${season}-${week}`;
        const isNewWeek = seededWeekKeyRef.current !== weekKey;
        seededWeekKeyRef.current = weekKey;
        setEditValues((prev) => {
          // A season/week change means these are different players'
          // saved values entirely (even a same-named player from a prior
          // week isn't the same row) -- reset and reseed from scratch.
          // Otherwise (e.g. a Game Environment save refreshed the whole
          // dataset) only seed rows that don't already have in-progress
          // edit state, so a save elsewhere never clobbers a field
          // someone's still mid-edit on.
          const next = isNewWeek ? {} : { ...prev };
          for (const row of result.players) {
            const key = playerKey(row);
            if (isNewWeek || !(key in next)) {
              next[key] = buildEditValues(row);
            }
          }
          return next;
        });
      })
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load player pool");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, contest]);

  useEffect(() => {
    load();
  }, [load]);

  const loadMyPool = useCallback(() => {
    fetchMyPlayerPool(season, week, platform, contest)
      .then((result) => setMyPoolMembers(new Set(result.players.map((p) => p.player))))
      .catch(() => {
        // Best-effort -- this grid's own load() above is what actually
        // gates the page; a My Player Pool hiccup just means the checkbox
        // column shows everyone as unchecked until the next successful
        // load, not a hard error here.
      });
  }, [season, week, platform, contest]);

  useEffect(() => {
    loadMyPool();
  }, [loadMyPool]);

  async function toggleMyPlayerPool(player: string) {
    const wasIn = myPoolMembers.has(player);
    setMyPoolMembers((prev) => {
      const next = new Set(prev);
      if (wasIn) next.delete(player);
      else next.add(player);
      return next;
    });
    setMyPoolSavingKeys((prev) => new Set(prev).add(player));
    try {
      await saveMyPlayerPoolEntry({ season, week, platform, contest, player, in_pool: !wasIn });
    } catch (err) {
      // Revert the optimistic flip on failure.
      setMyPoolMembers((prev) => {
        const next = new Set(prev);
        if (wasIn) next.add(player);
        else next.delete(player);
        return next;
      });
      setError(err instanceof Error ? err.message : "Failed to update My Player Pool");
    } finally {
      setMyPoolSavingKeys((prev) => {
        const next = new Set(prev);
        next.delete(player);
        return next;
      });
    }
  }

  async function saveRow(key: string) {
    const values = editValuesRef.current[key];
    if (!values) return;
    setSavingKeys((prev) => new Set(prev).add(key));
    try {
      await savePlayerPoolEntry({
        season,
        week,
        platform,
        player: key,
        game_environment: inputValueToScore(values.game_environment),
        game_matchup: inputValueToScore(values.game_matchup),
        ownership: inputValueToScore(values.ownership),
        salary_value: inputValueToScore(values.salary_value),
        volume: inputValueToScore(values.volume),
        talent: inputValueToScore(values.talent),
      });
      setDirtyKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save score");
    } finally {
      setSavingKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }

  function scheduleAutosave(key: string) {
    if (debounceTimers.current[key]) {
      clearTimeout(debounceTimers.current[key]);
    }
    // Safety net for edits that never blur the field -- switching to a
    // different app tab or closing the window doesn't fire blur, so
    // without this a change could sit unsaved indefinitely.
    debounceTimers.current[key] = setTimeout(() => {
      delete debounceTimers.current[key];
      saveRow(key);
    }, AUTOSAVE_DEBOUNCE_MS);
  }

  function updateCell(key: string, field: ScoreFieldKey, value: string) {
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

  function effectiveValue(key: string, field: ScoreFieldKey, row: PlayerPoolPlayer): number | null {
    const typed = inputValueToScore(editValues[key]?.[field]);
    if (field === "game_environment" && typed === null) {
      return row.game_environment_suggested;
    }
    return typed;
  }

  function liveTotal(key: string, row: PlayerPoolPlayer, fields: ScoreFieldConfig[]): number {
    return fields.reduce((sum, f) => {
      const v = effectiveValue(key, f.key, row);
      return v !== null ? sum + v : sum;
    }, 0);
  }

  async function handleApplyVegasLines() {
    setGameEnvScraping(true);
    setGameEnvScrapeMessage(null);
    try {
      const result = await applyVegasLines(season, week);
      setGameEnvScrapeMessage(
        result.skipped_count > 0
          ? `Updated ${result.applied_count} games (${result.skipped_count} skipped -- see below).`
          : `Updated ${result.applied_count} games.`
      );
      load();
    } catch (err) {
      setGameEnvScrapeMessage(err instanceof Error ? err.message : "Failed to update from Vegas Lines");
    } finally {
      setGameEnvScraping(false);
    }
  }

  const isNotFound = error !== null && error.includes("No DK salary file uploaded yet");

  // {game_key: GameEnvironmentEntry} for this week's Vegas Line popovers --
  // rebuilt only when the loaded data actually changes, not on every
  // render/keystroke.
  const gameEnvByKey = useMemo(() => {
    const map = new Map<string, GameEnvironmentEntry>();
    for (const entry of data?.game_environment ?? []) {
      map.set(entry.game_key, entry);
    }
    return map;
  }, [data]);

  const players = data?.players ?? [];
  const visiblePlayers = players.filter((p) => p.position === position);
  const fields = scoreFieldsForPosition(position);

  const saveStatus = savingKeys.size > 0 ? "Saving…" : dirtyKeys.size > 0 ? "Unsaved changes" : "All changes saved";

  return (
    <>
      <div className="filters">
        <div className="chip-filter">
          <span className="filter-label">Position</span>
          <div className="chip-row">
            {POSITIONS.map((p) => (
              <button
                key={p}
                type="button"
                className={`chip${position === p ? " selected" : ""}`}
                aria-pressed={position === p}
                onClick={() => setPosition(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && (
        <p className="hint">
          No DK salary file uploaded yet for season {season} week {week} -- upload it in the Settings tab.
        </p>
      )}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && data && (
        <>
          <section className="ownership-section">
            <div className="player-pool-grid-header">
              <h2>Player Rankings</h2>
              <span className="player-pool-save-status">{saveStatus}</span>
            </div>
            {/* Game Environment's own refresh now lives on that column's
                header (the ↻ icon next to its info icon below) rather than
                a standalone button/section -- this is just where its
                result message surfaces now that section is gone. */}
            {gameEnvUpdateMessage && <p className="hint">{gameEnvUpdateMessage}</p>}
            {visiblePlayers.length === 0 ? (
              <p className="hint">No {position} players loaded.</p>
            ) : (
              <div className="player-pool-grid-wrap">
                <table className="player-pool-grid">
                  <thead>
                    <tr>
                      <th className="player-pool-grid-sticky">Name</th>
                      <th>Salary</th>
                      <th>
                        Expected
                        <br />
                        FPTS ({resolvedMultiplierLabel(players)}x)
                      </th>
                      <th>Team</th>
                      <th>Opp</th>
                      <th>
                        My
                        <br />
                        Pool
                      </th>
                      {fields.map((f) => (
                        <th key={f.key}>
                          {f.key === "volume" ? (
                            <>
                              Vol/
                              <br />
                              Opp
                            </>
                          ) : f.key === "talent" ? (
                            <>
                              Talent/
                              <br />
                              Exp
                            </>
                          ) : f.key === "game_environment" ? (
                            <>
                              Game
                              <br />
                              Env
                            </>
                          ) : (
                            f.label
                          )}
                          {f.key === "game_environment" && (
                            <button
                              type="button"
                              className="header-refresh-icon"
                              disabled={gameEnvUpdating}
                              onClick={handleApplyVegasLines}
                              aria-label={gameEnvUpdating ? "Updating…" : "Update from Vegas Lines tab"}
                              title={gameEnvUpdating ? "Updating…" : "Update from Vegas Lines tab"}
                            >
                              ↻
                            </button>
                          )}
                          {f.key === "game_environment" && (
                            <HeaderInfoPopover title={f.label} lines={GAME_ENVIRONMENT_NOTES} />
                          )}
                          {f.key === "game_matchup" && <HeaderInfoPopover title={f.label} lines={GAME_MATCHUP_NOTES} />}
                          {f.key === "ownership" && <HeaderInfoPopover title={f.label} lines={OWNERSHIP_NOTES} />}
                          {f.key === "volume" && <HeaderInfoPopover title={f.label} lines={VOLUME_OPPORTUNITIES_NOTES} />}
                          {f.key === "talent" && <HeaderInfoPopover title={f.label} lines={TALENT_EXPLOSIVENESS_NOTES} />}
                        </th>
                      ))}
                      <th className="player-pool-grid-sticky-right">
                        Rank
                        <br />
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {visiblePlayers.map((row) => {
                      const key = playerKey(row);
                      const values = editValues[key] ?? {};
                      return (
                        <tr key={key} className={dirtyKeys.has(key) ? "player-pool-row-dirty" : undefined}>
                          <td className="player-pool-grid-sticky">{row.player}</td>
                          <td className="player-pool-grid-num">{formatSalary(row.salary)}</td>
                          <td className="player-pool-grid-num">{formatExpectedFpts(row.expected_fpts)}</td>
                          <td>{row.team}</td>
                          <td>{row.is_home === null ? row.opponent : row.is_home ? `vs ${row.opponent}` : `@${row.opponent}`}</td>
                          <td>
                            <input
                              type="checkbox"
                              className="player-pool-my-pool-checkbox"
                              checked={myPoolMembers.has(row.player)}
                              disabled={myPoolSavingKeys.has(row.player)}
                              onChange={() => toggleMyPlayerPool(row.player)}
                              aria-label={`Add ${row.player} to My Player Pool`}
                            />
                          </td>
                          {fields.map((f) => (
                            <td key={f.key}>
                              <input
                                type="number"
                                min={f.key === "game_environment" ? 0 : 1}
                                max={f.key === "game_environment" ? 1 : 3}
                                step={f.key === "game_environment" ? "0.5" : "0.25"}
                                title={
                                  DEFAULT_FALLBACK_FIELDS.has(f.key)
                                    ? "Falls back to the Settings Default until changed this week"
                                    : undefined
                                }
                                placeholder={
                                  f.key === "game_environment" && row.game_environment_suggested !== null
                                    ? String(row.game_environment_suggested)
                                    : undefined
                                }
                                value={values[f.key] ?? ""}
                                onChange={(e) => updateCell(key, f.key, e.target.value)}
                                onBlur={() => handleCellBlur(key)}
                              />
                              {f.key === "game_environment" && (
                                <HeaderInfoPopover
                                  ariaLabel="Vegas line for this game"
                                  lines={vegasLineNotes(gameEnvByKey.get(gameEnvKey(row.team, row.opponent)))}
                                />
                              )}
                              {f.key === "ownership" && row.ownership_pct !== null && (
                                <span className="player-pool-ownership-pct">
                                  {formatOwnershipPct(row.ownership_pct)}
                                </span>
                              )}
                            </td>
                          ))}
                          <td className="player-pool-grid-num player-pool-grid-total player-pool-grid-sticky-right">
                            {formatTotal(liveTotal(key, row, fields))}
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
      )}
    </>
  );
}
