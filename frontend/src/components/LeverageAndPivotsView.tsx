import { useEffect, useState } from "react";
import { fetchLeveragePivots } from "../api";
import type { LeveragePivotsResult, LpColumn, LpPlayer } from "../types";

// Leverage & Pivots tab. Everything shown arrives finished from
// GET /api/leverage-pivots (see backend/services/leverage_pivots/engine.py);
// this component only renders it and tracks which player/position is selected.

interface Props {
  season: number;
  week: number;
  platform: string;
}

const money = (n: number) => `$${n.toLocaleString()}`;
const pct = (n: number) => `${n.toFixed(1)}%`;

function Column({ column }: { column: LpColumn }) {
  return (
    <div className="lp-col">
      <div className="lp-col-top">
        <h3>{column.title}</h3>
        <p>{column.subtitle}</p>
      </div>
      <div className="lp-col-head">
        <span>{column.header}</span>
        <span>Price · Owned</span>
      </div>
      {column.rows.length === 0 && <div className="lp-empty">None</div>}
      {column.rows.map((r) => (
        <div className="lp-item" key={r.player}>
          <div>
            <b>{r.player}</b>
            <div className="lp-sub">
              {r.position} · {r.team}
            </div>
          </div>
          <div className="lp-right">
            {money(r.salary)}
            <div className="lp-sub">{r.salary_diff_label}</div>
          </div>
          <div className="lp-right">
            <span className={`lp-own${r.less_label === null ? " lp-own-corr" : ""}`}>{pct(r.ownership_pct)}</span>
            {r.less_label && <div className="lp-sub">{r.less_label}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function LeverageAndPivotsView({ season, week, platform }: Props) {
  const [data, setData] = useState<LeveragePivotsResult | null>(null);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [position, setPosition] = useState("All");
  const [chalkInput, setChalkInput] = useState("15");
  const [chalkPct, setChalkPct] = useState(15);
  const [minInput, setMinInput] = useState("3");
  const [minReasons, setMinReasons] = useState(3);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchLeveragePivots(season, week, platform, selectedName, position, chalkPct, minReasons)
      .then(setData)
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load leverage and pivots");
      })
      .finally(() => setLoading(false));
  }, [season, week, platform, selectedName, position, chalkPct, minReasons]);

  function select(player: LpPlayer | string) {
    const name = typeof player === "string" ? player : player.player;
    setSelectedName(name);
    setSearchText(name);
    setPosition("All");
  }

  function commitChalk(value: string) {
    const parsed = Number(value);
    if (value.trim() !== "" && Number.isFinite(parsed) && parsed >= 0 && parsed <= 100) {
      setChalkPct(parsed);
    } else {
      setChalkInput(String(chalkPct));
    }
  }

  function commitMin(value: string) {
    const parsed = Number(value);
    if (value.trim() !== "" && Number.isInteger(parsed) && parsed >= 1) {
      setMinReasons(parsed);
    } else {
      setMinInput(String(minReasons));
    }
  }

  function toggle(name: string) {
    setExpanded((cur) => {
      const next = new Set(cur);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  const selected = data?.selected ?? null;

  return (
    <>
      <div className="filters">
        <label className="game-logs-lookback-field">
          Chalk is owned at or above (%)
          <input
            type="text"
            inputMode="decimal"
            className="lp-chalk-input"
            value={chalkInput}
            onChange={(e) => setChalkInput(e.target.value)}
            onBlur={(e) => commitChalk(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitChalk(chalkInput);
            }}
          />
        </label>
        <label className="game-logs-lookback-field">
          Minimum leverage/pivot reasons
          <input
            type="text"
            inputMode="numeric"
            className="lp-chalk-input"
            value={minInput}
            onChange={(e) => setMinInput(e.target.value)}
            onBlur={(e) => commitMin(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitMin(minInput);
            }}
          />
        </label>
      </div>
      {loading && data === null && <p className="hint">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {data && (
        <>
          <section className="lp-panel">
            <h3>Players who are leverage or pivots against {minReasons} or more players</h3>
            <p className="lp-intro">Click a player to see who he is leverage or a pivot against.</p>
            {data.panel.length === 0 && <p className="hint">No player is leverage or a pivot against {minReasons} or more players.</p>}
            {data.panel.map((group) => (
              <div key={group.reason_count}>
                <div className="lp-group">{group.reason_count} reasons</div>
                {group.players.map((p) => {
                  const open = expanded.has(p.player);
                  return (
                    <div key={p.player}>
                      <div className="lp-prow" onClick={() => toggle(p.player)}>
                        <div>
                          <span>{open ? "▾" : "▸"}</span> <b>{p.player}</b>{" "}
                          <span className="lp-sub">
                            {p.position} · {p.team}
                          </span>
                          <span className="lp-badge">{p.reasons.length} players</span>
                        </div>
                        <div className="lp-right">
                          {money(p.salary)} <span className="lp-own">{pct(p.ownership_pct)}</span>
                        </div>
                      </div>
                      {open && (
                        <div className="lp-why">
                          {p.reasons.map((r, i) => (
                            <div key={i}>
                              <span className={`lp-tag lp-tag-${r.kind}`}>{r.label}</span>
                              {r.text}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </section>

          <p className="lp-label">This week's chalk ({data.leverage_point}% or more)</p>
          {data.chalk.map((g) => (
            <div className="lp-chalk-row" key={g.position}>
              <b>{g.position}</b>
              <div className="chip-row">
                {g.players.map((p) => (
                  <button
                    key={p.player}
                    type="button"
                    className={`chip${selectedName === p.player ? " selected" : ""}`}
                    aria-pressed={selectedName === p.player}
                    onClick={() => select(p)}
                  >
                    {p.player} <span className="lp-chip-own">{pct(p.ownership_pct)}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}

          <p className="lp-label">Or any player</p>
          <input
            type="text"
            list="lp-player-names"
            className="lp-search"
            value={searchText}
            placeholder="Type a player name"
            onChange={(e) => {
              setSearchText(e.target.value);
              if (data.search_names.includes(e.target.value)) select(e.target.value);
            }}
          />
          <datalist id="lp-player-names">
            {data.search_names.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
          {data.selected_not_found && <p className="hint">That player isn't on this slate.</p>}

          {selected && (
            <>
              <div className="lp-banner">
                <div>
                  <span className="lp-sub lp-upper">Instead of</span> <b className="lp-banner-name">{selected.trigger.player}</b>
                  <div className="lp-sub">
                    {selected.trigger.position} · {selected.game_label} · {money(selected.trigger.salary)}
                  </div>
                </div>
                <div className="lp-banner-own">
                  {pct(selected.trigger.ownership_pct)}
                  <span className="lp-sub"> owned</span>
                </div>
              </div>

              <div className="chip-row lp-pos-chips">
                {["All", ...selected.position_counts.map(([p]) => p)].map((p) => {
                  const count = selected.position_counts.find(([pos]) => pos === p)?.[1];
                  return (
                    <button
                      key={p}
                      type="button"
                      className={`chip${position === p ? " selected" : ""}`}
                      aria-pressed={position === p}
                      onClick={() => setPosition(p)}
                    >
                      {p}
                      {count !== undefined && <span className="lp-chip-own"> {count}</span>}
                    </button>
                  );
                })}
              </div>

              <div className="lp-cols">
                <Column column={selected.leverage} />
                <Column column={selected.correlated} />
                <Column column={selected.position_pivot} />
                <Column column={selected.pricing_pivot} />
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
