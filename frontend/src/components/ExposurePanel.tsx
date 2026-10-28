import { useEffect, useState } from "react";
import type { ExposureView } from "../types";

interface ExposurePanelProps {
  title: string;
  // Fetches the finished view from the backend -- nothing is calculated here.
  load: (scope: string, position: string, sort: string, compare: boolean) => Promise<ExposureView | null>;
  // Change to refetch (e.g. after a new analysis or week).
  reloadKey: string;
  initialScope?: string;
  showCompare?: boolean;
  emptyMessage?: string;
}

const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "DST"];
const FLEX_CLASS: Record<string, string> = { RB: "exposure-flex-rb", WR: "exposure-flex-wr", TE: "exposure-flex-te" };

export function ExposurePanel({ title, load, reloadKey, initialScope, showCompare = false, emptyMessage }: ExposurePanelProps) {
  const [scope, setScope] = useState(initialScope ?? "");
  const [position, setPosition] = useState("ALL");
  const [sort, setSort] = useState("exposure");
  const [compare, setCompare] = useState(false);
  const [view, setView] = useState<ExposureView | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    load(scope, position, sort, compare)
      .then((v) => {
        if (cancelled) return;
        setView(v);
        setLoaded(true);
        setError(null);
        if (v && scope === "") setScope(v.selected);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e.message ?? e));
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, position, sort, compare, reloadKey]);

  if (error) return <p className="exposure-error">{error}</p>;
  if (loaded && !view) return <p className="exposure-hint">{emptyMessage ?? "No exposure data yet."}</p>;
  if (!view) return <p className="exposure-hint">Loading…</p>;

  const sorts: [string, string][] = [["exposure", "Exposure"], ["diff", "Difference"], [view.has_pts ? "pts" : "salary", view.has_pts ? "Points" : "Salary"]];

  return (
    <div className="exposure-panel">
      <h3>{title}</h3>
      <div className="exposure-row">
        <span className="exposure-label">Lineups</span>
        {view.scopes.map((s) => (
          <button key={s.key} type="button" className={s.key === view.selected ? "" : "secondary"} onClick={() => setScope(s.key)}>
            {s.label}
          </button>
        ))}
      </div>

      <div className="exposure-flex">
        <div className="exposure-flex-title">FLEX position</div>
        <div className="exposure-flex-bar">
          {view.flex
            .filter((f) => f.count > 0)
            .map((f) => (
              <div key={f.position} className={FLEX_CLASS[f.position]} style={{ width: `${f.pct}%` }}>
                {f.position}
              </div>
            ))}
        </div>
        <div className="exposure-flex-legend">
          {view.flex.map((f) => (
            <span key={f.position}>
              {f.position} <b>{f.count}</b> lineups ({f.pct.toFixed(0)}%)
            </span>
          ))}
        </div>
      </div>

      <div className="exposure-row">
        <span className="exposure-label">Position</span>
        {POSITIONS.map((p) => (
          <button key={p} type="button" className={p === position ? "" : "secondary"} onClick={() => setPosition(p)}>
            {p === "ALL" ? "All" : p}
          </button>
        ))}
        <span className="exposure-label exposure-gap">Sort</span>
        {sorts.map(([key, label]) => (
          <button key={key} type="button" className={key === sort ? "" : "secondary"} onClick={() => setSort(key)}>
            {label}
          </button>
        ))}
        {showCompare && (
          <label className="exposure-compare" title={view.compare_available ? "" : "No analyzed pool saved for this week"}>
            <input type="checkbox" checked={compare} disabled={!view.compare_available} onChange={(e) => setCompare(e.target.checked)} /> Compare
            with my analyzed pool
          </label>
        )}
      </div>

      <div className="exposure-table-wrap">
        <table className="exposure-table">
          <thead>
            <tr>
              <th className="exposure-left">Player</th>
              <th>Pos</th>
              <th>Salary</th>
              {view.has_pts && <th>Pts</th>}
              <th>Lineups</th>
              <th className="exposure-left">Exposure</th>
              <th>{view.field_label}</th>
              <th>Diff</th>
              {compare && view.compare_available && <th>My pool</th>}
            </tr>
          </thead>
          <tbody>
            {view.players.map((p) => (
              <tr key={p.name}>
                <td className="exposure-left">
                  {p.name} <span className="exposure-team">{p.team}</span>
                </td>
                <td>{p.position}</td>
                <td>${p.salary.toLocaleString()}</td>
                {view.has_pts && <td>{p.pts === null ? "—" : p.pts.toFixed(1)}</td>}
                <td>{p.count}</td>
                <td className="exposure-left">
                  <span className="exposure-bar" style={{ width: `${Math.min(p.exposure_pct, 100) * 1.2}px` }} />
                  {p.exposure_pct.toFixed(0)}%
                </td>
                <td>{p.field_pct === null ? "—" : `${p.field_pct.toFixed(0)}%`}</td>
                <td className={p.diff === null ? "" : p.diff >= 0 ? "exposure-pos" : "exposure-neg"}>
                  {p.diff === null ? "—" : `${p.diff >= 0 ? "+" : ""}${p.diff.toFixed(0)}`}
                </td>
                {compare && view.compare_available && <td>{p.compare_pct === null ? "—" : `${p.compare_pct.toFixed(0)}%`}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="exposure-hint">
        Exposure is the share of the selected lineups that roster the player. Diff is exposure minus {view.field_label.toLowerCase()}: positive
        means more exposure than the field.
      </p>
    </div>
  );
}
