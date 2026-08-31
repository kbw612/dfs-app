import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPlayerPool, saveGameEnvironment, savePlayerAttributeEntry, savePlayerPoolEntry } from "../api";
import type { GameEnvironmentEntry, PlayerPoolPlayer, PlayerPoolResult } from "../types";
import { formatSalary } from "./playerDisplay";

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
  { key: "game_environment", label: "Game env" },
  { key: "game_matchup", label: "Matchup" },
  { key: "ownership", label: "Ownership" },
  { key: "volume", label: "Volume" },
  { key: "talent", label: "Talent" },
];

const DST_SCORE_FIELDS: ScoreFieldConfig[] = [
  { key: "game_matchup", label: "Matchup" },
  { key: "salary_value", label: "Salary value" },
];

function scoreFieldsForPosition(position: string): ScoreFieldConfig[] {
  return position === "DST" ? DST_SCORE_FIELDS : OFFENSE_SCORE_FIELDS;
}

// Fields that carry forward from the most recent earlier week when left
// blank (see entries_repo.resolve_carry_forward_value).
const CARRY_FORWARD_FIELDS = new Set<ScoreFieldKey>(["volume", "talent"]);

const POSITIONS = ["QB", "RB", "WR", "TE", "DST"] as const;
type Position = (typeof POSITIONS)[number];

const AUTOSAVE_DEBOUNCE_MS = 800;

function formatTotal(total: number): string {
  return total % 1 === 0 ? String(total) : total.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
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
// leaving the Game env cell blank and saving should mean "keep using the
// formula's suggestion," not "freeze in whatever it happened to suggest
// right now" (see types.ts's PlayerPoolPlayer docstring).
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
}

export function PlayerPoolView({ season, week, platform }: PlayerPoolViewProps) {
  const [data, setData] = useState<PlayerPoolResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [position, setPosition] = useState<Position>("QB");
  const [editValues, setEditValues] = useState<Record<string, EditValues>>({});
  const [dirtyKeys, setDirtyKeys] = useState<Set<string>>(new Set());
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());
  const [showGameEnvironment, setShowGameEnvironment] = useState(false);
  const [gameEnvEdits, setGameEnvEdits] = useState<Record<string, Partial<GameEnvironmentEntry>>>({});
  const [gameEnvSaving, setGameEnvSaving] = useState<string | null>(null);

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

    fetchPlayerPool(season, week, platform)
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
  }, [season, week, platform]);

  useEffect(() => {
    load();
  }, [load]);

  async function saveRow(key: string) {
    const values = editValuesRef.current[key];
    if (!values) return;
    setSavingKeys((prev) => new Set(prev).add(key));
    try {
      // Two separate resources now (see backend/schemas/player_attributes)
      // -- Volume/Talent split out of Player Pool's own entry, so a full
      // row save is two PUTs instead of one. Both fire regardless of
      // which specific cell changed; simpler than tracking which resource
      // a given field belongs to, and idempotent either way.
      await Promise.all([
        savePlayerPoolEntry({
          season,
          week,
          player: key,
          game_environment: inputValueToScore(values.game_environment),
          game_matchup: inputValueToScore(values.game_matchup),
          ownership: inputValueToScore(values.ownership),
          salary_value: inputValueToScore(values.salary_value),
        }),
        savePlayerAttributeEntry({
          season,
          week,
          player: key,
          volume: inputValueToScore(values.volume),
          talent: inputValueToScore(values.talent),
        }),
      ]);
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

  function updateGameEnvField(gameKey: string, field: keyof GameEnvironmentEntry, value: string) {
    setGameEnvEdits((prev) => ({ ...prev, [gameKey]: { ...prev[gameKey], [field]: value } }));
  }

  async function saveGameEnv(gameKey: string, homeTeam: string, awayTeam: string) {
    const edits = gameEnvEdits[gameKey] ?? {};
    const parseOrNull = (v: unknown) => (v === undefined || v === "" ? null : Number(v));
    setGameEnvSaving(gameKey);
    try {
      await saveGameEnvironment({
        season,
        week,
        game_key: gameKey,
        home_team: homeTeam,
        away_team: awayTeam,
        home_spread: parseOrNull(edits.home_spread),
        over_under: parseOrNull(edits.over_under),
        home_implied_total: parseOrNull(edits.home_implied_total),
        away_implied_total: parseOrNull(edits.away_implied_total),
      });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save game environment");
    } finally {
      setGameEnvSaving(null);
    }
  }

  const isNotFound = error !== null && error.includes("No DK salary file uploaded yet");

  const players = data?.players ?? [];
  const visiblePlayers = players.filter((p) => p.position === position);
  const fields = scoreFieldsForPosition(position);
  const gameEnvByKey = new Map((data?.game_environment ?? []).map((g) => [g.game_key, g]));

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
          <section className="ownership-section player-pool-game-environment">
            <button
              type="button"
              className="player-pool-game-environment-toggle"
              onClick={() => setShowGameEnvironment((v) => !v)}
            >
              Game Environment inputs (per game) {showGameEnvironment ? "▴" : "▾"}
            </button>
            {showGameEnvironment && (
              <ul className="ownership-player-list pivot-card-list player-pool-game-environment-list">
                {data.games.map((game) => {
                  const [away, home] = game.key.split("-");
                  const saved = gameEnvByKey.get(game.key);
                  const edits = gameEnvEdits[game.key] ?? {};
                  const homeSpread = edits.home_spread ?? scoreToInputValue(saved?.home_spread ?? null);
                  const overUnder = edits.over_under ?? scoreToInputValue(saved?.over_under ?? null);
                  const homeTotal = edits.home_implied_total ?? scoreToInputValue(saved?.home_implied_total ?? null);
                  const awayTotal = edits.away_implied_total ?? scoreToInputValue(saved?.away_implied_total ?? null);
                  return (
                    <li key={game.key} className="ownership-pivot-group player-pool-game-environment-row">
                      <span className="player-pool-game-label">{game.label}</span>
                      <label>
                        {home} spread
                        <input
                          type="number"
                          step="0.5"
                          value={homeSpread}
                          onChange={(e) => updateGameEnvField(game.key, "home_spread", e.target.value)}
                        />
                      </label>
                      <label>
                        O/U
                        <input
                          type="number"
                          step="0.5"
                          value={overUnder}
                          onChange={(e) => updateGameEnvField(game.key, "over_under", e.target.value)}
                        />
                      </label>
                      <label>
                        {home} total
                        <input
                          type="number"
                          step="0.5"
                          value={homeTotal}
                          onChange={(e) => updateGameEnvField(game.key, "home_implied_total", e.target.value)}
                        />
                      </label>
                      <label>
                        {away} total
                        <input
                          type="number"
                          step="0.5"
                          value={awayTotal}
                          onChange={(e) => updateGameEnvField(game.key, "away_implied_total", e.target.value)}
                        />
                      </label>
                      <button
                        type="button"
                        className="player-pool-save-button"
                        disabled={gameEnvSaving === game.key}
                        onClick={() => saveGameEnv(game.key, home, away)}
                      >
                        {gameEnvSaving === game.key ? "Saving…" : "Save"}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="ownership-section">
            <div className="player-pool-grid-header">
              <h2>Player Pool</h2>
              <span className="player-pool-save-status">{saveStatus}</span>
            </div>
            {visiblePlayers.length === 0 ? (
              <p className="hint">No {position} players loaded.</p>
            ) : (
              <div className="player-pool-grid-wrap">
                <table className="player-pool-grid">
                  <thead>
                    <tr>
                      <th className="player-pool-grid-sticky">Name</th>
                      <th>Salary</th>
                      <th>Team</th>
                      <th>Opp</th>
                      {fields.map((f) => (
                        <th key={f.key}>{f.label}</th>
                      ))}
                      <th>Total</th>
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
                          <td>{row.team}</td>
                          <td>{row.is_home === null ? row.opponent : row.is_home ? `vs ${row.opponent}` : `@${row.opponent}`}</td>
                          {fields.map((f) => (
                            <td key={f.key}>
                              <input
                                type="number"
                                min={1}
                                max={3}
                                step="0.25"
                                title={CARRY_FORWARD_FIELDS.has(f.key) ? "Carries forward until changed" : undefined}
                                placeholder={
                                  f.key === "game_environment" && row.game_environment_suggested !== null
                                    ? String(row.game_environment_suggested)
                                    : undefined
                                }
                                value={values[f.key] ?? ""}
                                onChange={(e) => updateCell(key, f.key, e.target.value)}
                                onBlur={() => handleCellBlur(key)}
                              />
                            </td>
                          ))}
                          <td className="player-pool-grid-num player-pool-grid-total">
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
