import { useEffect, useRef, useState } from "react";
import { fetchPlayerSignals } from "../api";
import type { PlayerSignalsResult, SignalChip, SignalPlayer } from "../types";
import { HideBelowField } from "./HideBelowField";
import { formatOwnershipPct } from "./playerDisplay";

// Player Pool Signals tab. Every chip, count and threshold arrives finished from
// GET /api/player-signals (see backend/services/player_signals/engine.py); this
// component only renders them and tracks the controls.

interface Props {
  season: number;
  week: number;
  platform: string;
}

const POSITIONS = ["All", "QB", "RB", "WR", "TE", "DST"];
const MIN_NET_OPTIONS = Array.from({ length: 16 }, (_, i) => i - 5);
const GROUPS = ["RB", "WR / TE", "QB / DST", "All"];

function Chip({ chip }: { chip: SignalChip }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const hasDetail = chip.detail.length > 0;
  const cls = chip.polarity === "down" ? "sig-chip sig-down" : `sig-chip sig-${chip.family}`;

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!hasDetail) return <span className={cls}>{chip.text}</span>;
  return (
    <span className="sig-wrap" ref={ref}>
      <button
        type="button"
        className={`${cls} sig-button`}
        aria-expanded={open}
        aria-label={`${chip.text}. Show games`}
        onClick={() => setOpen((v) => !v)}
      >
        {chip.text}
        <span className="sig-info" aria-hidden="true">
          ⓘ
        </span>
      </button>
      {open && (
        <span className="sig-pop" role="tooltip">
          {chip.detail.map((d, i) => (
            <span key={i}>{d}</span>
          ))}
        </span>
      )}
    </span>
  );
}

export function PlayerSignalsView({ season, week, platform }: Props) {
  const [data, setData] = useState<PlayerSignalsResult | null>(null);
  const [lastText, setLastText] = useState("5");
  const [lastWeeks, setLastWeeks] = useState(5);
  const [minNet, setMinNet] = useState(3);
  const [hideBelow, setHideBelow] = useState(1);
  const [position, setPosition] = useState("All");
  const [sort, setSort] = useState("signals");
  const [oppScope, setOppScope] = useState("last");
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [panelOpen, setPanelOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchPlayerSignals(season, week, platform, lastWeeks, minNet, hideBelow, overrides, oppScope)
      .then(setData)
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load player signals");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, lastWeeks, minNet, hideBelow, overrides, oppScope]);

  function commitLast(value: string) {
    const parsed = Number(value);
    if (value.trim() !== "" && Number.isInteger(parsed) && parsed >= 1) setLastWeeks(parsed);
    else setLastText(String(lastWeeks));
  }

  function commitThreshold(key: string, defaultValue: number, current: number) {
    const text = draft[key];
    if (text === undefined) return;
    const parsed = Number(text);
    setDraft((d) => {
      const { [key]: _gone, ...rest } = d;
      return rest;
    });
    if (text.trim() === "" || !Number.isFinite(parsed) || parsed === current) return;
    setOverrides((o) => {
      const next = { ...o };
      if (parsed === defaultValue) delete next[key];
      else next[key] = parsed;
      return next;
    });
  }

  const rows: SignalPlayer[] = (data?.players ?? [])
    .filter((p) => position === "All" || p.position === position)
    .slice()
    .sort((a, b) => {
      if (sort === "salary") return b.salary - a.salary;
      if (sort === "own") return (b.ownership_pct ?? -1) - (a.ownership_pct ?? -1);
      return b.net - a.net || b.up - a.up || b.salary - a.salary;
    });

  return (
    <>
      <div className="filters">
        <label className="game-logs-lookback-field">
          Last
          <input
            type="text"
            inputMode="numeric"
            className="lp-chalk-input"
            value={lastText}
            onChange={(e) => setLastText(e.target.value)}
            onBlur={(e) => commitLast(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitLast(lastText);
            }}
          />
          weeks
        </label>
        <label className="game-logs-lookback-field">
          Min net signals
          <select value={minNet} onChange={(e) => setMinNet(Number(e.target.value))}>
            {MIN_NET_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="game-logs-lookback-field">
          Opponent history
          <select value={oppScope} onChange={(e) => setOppScope(e.target.value)}>
            <option value="last">Last X weeks</option>
            <option value="season">Season</option>
          </select>
        </label>
        <label className="game-logs-lookback-field">
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="signals">Signals</option>
            <option value="salary">Salary</option>
            <option value="own">Own %</option>
          </select>
        </label>
        <HideBelowField value={hideBelow} onChange={setHideBelow} />
      </div>

      <div className="sig-panel">
        <div
          className="sig-panel-head"
          role="button"
          tabIndex={0}
          aria-expanded={panelOpen}
          onClick={() => setPanelOpen((v) => !v)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setPanelOpen((v) => !v);
            }
          }}
        >
          <span>
            Thresholds
            {Object.keys(overrides).length > 0 ? ` (${Object.keys(overrides).length} changed)` : ""}
          </span>
          <span>
            {panelOpen && Object.keys(overrides).length > 0 && (
              <button
                type="button"
                className="sig-reset"
                onClick={(e) => {
                  e.stopPropagation();
                  setOverrides({});
                }}
              >
                Reset to defaults
              </button>
            )}
            <span className="ownership-summary-collapse-icon">{panelOpen ? "▴" : "▾"}</span>
          </span>
        </div>
        {panelOpen && data && (
          <div className="sig-panel-body">
            {GROUPS.map((group) => (
              <div className="sig-group" key={group}>
                <div className="sig-group-title">{group}</div>
                {data.thresholds
                  .filter((t) => t.group === group)
                  .map((t) => (
                    <label className="sig-threshold" key={t.key}>
                      {t.label}
                      <input
                        type="text"
                        inputMode="decimal"
                        value={draft[t.key] ?? String(t.value)}
                        onChange={(e) => setDraft((d) => ({ ...d, [t.key]: e.target.value }))}
                        onBlur={() => commitThreshold(t.key, t.default, t.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitThreshold(t.key, t.default, t.value);
                        }}
                      />
                    </label>
                  ))}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="chip-row sig-legend-row">
        {POSITIONS.map((pos) => (
          <button
            key={pos}
            type="button"
            className={`chip${position === pos ? " selected" : ""}`}
            aria-pressed={position === pos}
            onClick={() => setPosition(pos)}
          >
            {pos}
          </button>
        ))}
        <span className="sig-legend">
          <span className="sig-chip sig-usage">Usage</span>
          <span className="sig-chip sig-matchup">Matchup</span>
          <span className="sig-chip sig-game">Game</span>
          <span className="sig-chip sig-role">Role</span>
          <span className="sig-chip sig-price">Price / own</span>
          <span className="sig-chip sig-down">Negative</span>
        </span>
      </div>

      {data?.ownership_missing && (
        <p className="hint">
          No ownership file uploaded for this week, so players come from the DK salary file and ownership-based signals are
          off. Upload ownership projections in Settings to turn them on.
        </p>
      )}
      {loading && <p className="hint">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {data && !loading && (
        <p className="hint">
          {rows.length} of {data.total_players} players at net {data.min_net} or more. Usage from weeks {data.first_week}
          –{data.through_week}; opponent history is {data.opponent_scope === "season" ? "the whole season" : "the same weeks"}. Tap a chip with ⓘ for the games behind it.
        </p>
      )}

      {data && rows.length > 0 && (
        <table className="sig-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Salary</th>
              <th>Own</th>
              <th>Pts last {data.last_weeks}</th>
              <th>Net signals</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={`${p.position}-${p.player}`}>
                <td>
                  {p.player}
                  <div className="sig-sub">
                    {p.position} · {p.team} vs {p.opponent}
                    {p.status && <span className="player-status"> {p.status}</span>}
                  </div>
                </td>
                <td>${p.salary.toLocaleString()}</td>
                <td>{p.ownership_pct === null ? "" : formatOwnershipPct(p.ownership_pct)}</td>
                <td>{p.pts_last_x === null ? "" : p.pts_last_x.toFixed(1)}</td>
                <td className="sig-net">
                  {p.net}
                  <div className="sig-sub">
                    {p.up} up, {p.down} down
                  </div>
                </td>
                <td>
                  {p.signals.map((c, i) => (
                    <Chip chip={c} key={i} />
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && !loading && rows.length === 0 && <p className="hint">No players at this net signal count.</p>}
    </>
  );
}
