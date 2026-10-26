import { useEffect, useMemo, useState } from "react";
import { analyzeLineups, fetchLineupAnalyzerInfo, fetchLineupAnalyzerSaved, uploadLineupAnalyzerFiles } from "../api";
import type { LineupAnalyzerInfo, LineupAnalyzerResult, LineupAnalyzerRow } from "../types";
import { CollapsibleHint } from "./CollapsibleHint";

interface LineupAnalyzerViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

const FEATURE_LABELS: Record<string, string> = {
  own_sum: "Total ownership",
  log_own_prod: "Rarity (log own.)",
  max_own: "Biggest chalk player",
  n_chalk: "# chalk (20%+)",
  n_low: "# low-owned (3%-)",
  qb_own: "QB ownership",
  unused_k: "Unused salary ($K)",
  n_stars: "# stars ($8K+)",
  n_punts: "# punts ($4.5K-)",
  qb_mates: "QB teammates",
  bringback: "Bring-back",
  game_stack: "Game stack size",
  dst_conflict: "Offense vs own DST",
  proj_sum: "Projected points (sum)",
  ceiling_sum: "Ceiling points (sum)",
  qb_game_total: "QB game total (O/U)",
  avg_team_implied: "Avg offense implied total",
  dst_opp_implied: "DST opponent implied total",
};

const FIELD_SIZES = [100000, 150000, 317000, 500000];

function csvFor(rows: LineupAnalyzerRow[]): string {
  const header = "QB,RB,RB,WR,WR,WR,TE,FLEX,DST";
  const lines = rows.map((r) => r.players.map((p) => p.dk_id).join(","));
  return [header, ...lines].join("\n");
}

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function LineupRows({ row, featureNames }: { row: LineupAnalyzerRow; featureNames: string[] }) {
  return (
    <tr className="lineup-analyzer-detail">
      <td colSpan={7}>
        <div className="lineup-analyzer-breakdown">
          {featureNames.map((f) => {
            const c = row.contributions[f] ?? 0;
            return (
              <span key={f} className={c > 0.05 ? "pos" : c < -0.05 ? "neg" : ""}>
                {FEATURE_LABELS[f] ?? f}: {row.features[f]} ({c > 0 ? "+" : ""}
                {c.toFixed(2)})
              </span>
            );
          })}
        </div>
      </td>
    </tr>
  );
}

function LineupTable({ rows, featureNames }: { rows: LineupAnalyzerRow[]; featureNames: string[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="lineup-analyzer-table-wrap">
      <table className="lineup-analyzer-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Score</th>
            <th>Pctl</th>
            <th>Tier</th>
            <th>Players (salary, own %)</th>
            <th>Unused</th>
            <th>Own sum</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <FragmentRow key={r.rank} row={r} featureNames={featureNames} open={open === r.rank} onToggle={() => setOpen(open === r.rank ? null : r.rank)} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FragmentRow({ row, featureNames, open, onToggle }: { row: LineupAnalyzerRow; featureNames: string[]; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr className="lineup-analyzer-row" onClick={onToggle}>
        <td>{row.rank}</td>
        <td>{row.score.toFixed(2)}</td>
        <td>{row.percentile.toFixed(1)}</td>
        <td>{row.tier}</td>
        <td>
          {row.players.map((p) => (
            <span key={p.slot + p.name} className="lineup-analyzer-player" title={`${p.slot} ${p.team} $${p.salary} ${p.own}%`}>
              {p.name} <small>{p.salary / 1000}K · {p.own}%</small>
            </span>
          ))}
        </td>
        <td>${row.unused}</td>
        <td>{row.own_sum}</td>
      </tr>
      {open && <LineupRows row={row} featureNames={featureNames} />}
    </>
  );
}

export function LineupAnalyzerView({ season, week, platform, contest }: LineupAnalyzerViewProps) {
  const [info, setInfo] = useState<LineupAnalyzerInfo | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [append, setAppend] = useState(false);
  const [fieldSize, setFieldSize] = useState(317000);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [portfolioOn, setPortfolioOn] = useState(false);
  const [size, setSize] = useState(150);
  const [exposure, setExposure] = useState(50);
  const [overlap, setOverlap] = useState(6);
  const [result, setResult] = useState<LineupAnalyzerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [tab, setTab] = useState<"ranked" | "portfolio">("ranked");

  useEffect(() => {
    setResult(null);
    setSavedAt(null);
    setError(null);
    // Pool info + defaults first, then the last saved analysis (which also
    // restores the weights/portfolio settings it was run with).
    fetchLineupAnalyzerInfo(season, week, platform, contest)
      .then(async (i) => {
        setInfo(i);
        setWeights(i.default_weights);
        const saved = await fetchLineupAnalyzerSaved(season, week, platform, contest);
        if (!saved) return;
        setResult(saved.result);
        setSavedAt(saved.saved_at);
        setFieldSize(saved.request.field_size);
        setWeights({ ...i.default_weights, ...(saved.request.weights ?? {}) });
        const pf = saved.request.portfolio;
        setPortfolioOn(pf !== null);
        if (pf) {
          setSize(pf.size);
          setExposure(pf.max_exposure_pct);
          setOverlap(pf.max_overlap);
        }
        setTab("ranked");
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, [season, week, platform, contest]);

  // Re-check the slate inputs when the window regains focus and every 30s, so
  // a changed ownership upload (Settings tab) offers a re-analyze here.
  const [currentSignature, setCurrentSignature] = useState<string | null>(null);
  useEffect(() => {
    const check = () =>
      fetchLineupAnalyzerInfo(season, week, platform, contest)
        .then((i) => setCurrentSignature(i.slate_signature))
        .catch(() => undefined);
    check();
    const timer = window.setInterval(check, 30000);
    window.addEventListener("focus", check);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, [season, week, platform, contest]);
  const stale = result !== null && currentSignature !== null && currentSignature !== result.slate_signature;

  const run = async (currentWeights = weights) => {
    setBusy(true);
    setError(null);
    try {
      const res = await analyzeLineups({
        season,
        week,
        platform,
        contest,
        field_size: fieldSize,
        weights: currentWeights,
        limit: 300,
        portfolio: portfolioOn ? { size, max_exposure_pct: exposure, max_overlap: overlap } : null,
      });
      setResult(res);
      setSavedAt(new Date().toISOString());
      if (!res.portfolio) setTab("ranked");
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    setBusy(true);
    setError(null);
    try {
      const i = await uploadLineupAnalyzerFiles(season, week, platform, contest, files, !append);
      setInfo(i);
      setFiles([]);
      setResult(null);
      setSavedAt(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const features = info?.feature_names ?? [];
  const shown = useMemo(() => (tab === "portfolio" ? result?.portfolio ?? [] : result?.rows ?? []), [tab, result]);

  return (
    <div className="lineup-analyzer">
      <h2>Lineup Analyzer</h2>
      <CollapsibleHint
        items={[
          "Each lineup is scored on structural factors (ownership, salary use, stacking) measured against a simulated field built from this week's projected ownership.",
          "Default weights were fitted on 2025 main slates (317K-entry contests): real top-0.1% lineups versus that simulated field.",
          "The score is a profile match to top finishers, not a win probability. Percentile is the lineup's rank within the simulated field.",
          "Click a row to see each factor's value and contribution.",
        ]}
      />

      <section className="lineup-analyzer-section">
        <h3>1. Lineup files</h3>
        <div className="lineup-analyzer-controls">
          <input type="file" accept=".csv" multiple onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
          <label>
            <input type="checkbox" checked={append} onChange={(e) => setAppend(e.target.checked)} /> Add to existing pool
          </label>
          <button type="button" disabled={busy || files.length === 0} onClick={upload}>
            Upload {files.length || ""} file{files.length === 1 ? "" : "s"}
          </button>
        </div>
        {info && info.lineup_count > 0 && (
          <p className="lineup-analyzer-note">
            {info.lineup_count.toLocaleString()} unique lineups from {info.files.length} file(s):{" "}
            {info.files.map((f) => `${f.name} (${f.rows} rows, ${f.new_unique} new)`).join("; ")}
          </p>
        )}
      </section>

      <section className="lineup-analyzer-section">
        <h3>2. Settings</h3>
        <div className="lineup-analyzer-controls">
          <label>
            Contest size{" "}
            <select value={fieldSize} onChange={(e) => setFieldSize(Number(e.target.value))}>
              {FIELD_SIZES.map((s) => (
                <option key={s} value={s}>
                  {s.toLocaleString()}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input type="checkbox" checked={portfolioOn} onChange={(e) => setPortfolioOn(e.target.checked)} /> Build portfolio
          </label>
          {portfolioOn && (
            <>
              <label>
                Lineups <input type="number" min={1} max={1000} value={size} onChange={(e) => setSize(Number(e.target.value))} />
              </label>
              <label>
                Max player exposure %{" "}
                <input type="number" min={1} max={100} value={exposure} onChange={(e) => setExposure(Number(e.target.value))} />
              </label>
              <label>
                Max shared players{" "}
                <input type="number" min={0} max={8} value={overlap} onChange={(e) => setOverlap(Number(e.target.value))} />
              </label>
            </>
          )}
        </div>
        <details>
          <summary>Factor weights ({features.length})</summary>
          <p className="lineup-analyzer-note">
            The last five (projected/ceiling points and game environment) default to 0: a 2026 weeks 1-6 check found
            no reliable signal in them, so set them yourself if you want to lean on them.
          </p>
          <div className="lineup-analyzer-weights">
            {features.map((f) => (
              <label key={f}>
                {FEATURE_LABELS[f] ?? f}
                <input
                  type="number"
                  step={0.1}
                  value={weights[f] ?? 0}
                  onChange={(e) => setWeights({ ...weights, [f]: Number(e.target.value) })}
                />
              </label>
            ))}
            <button type="button" onClick={() => info && setWeights(info.default_weights)}>
              Reset to fitted defaults
            </button>
          </div>
        </details>
        <button type="button" disabled={busy || !info || info.lineup_count === 0} onClick={() => run()}>
          {busy ? "Working…" : "Analyze lineups"}
        </button>
        {error && <p className="lineup-analyzer-error">{error}</p>}
      </section>

      {result && (
        <section className="lineup-analyzer-section">
          <h3>3. Results</h3>
          <p className="lineup-analyzer-note">
            {savedAt && `Saved ${new Date(savedAt).toLocaleString()}. `}
            {result.total.toLocaleString()} lineups scored
            {result.unresolved > 0 && ` (${result.unresolved} skipped: players not in this slate)`}. Top 1% of a{" "}
            {result.field_size.toLocaleString()}-entry contest = {result.top_1pct_entries.toLocaleString()} entries.{" "}
            {Object.entries(result.tier_counts)
              .map(([t, n]) => `${t}: ${n}`)
              .join(" · ")}
          </p>
          {stale && (
            <p className="lineup-analyzer-stale">
              Ownership projections, salaries or Vegas lines changed since this analysis.{" "}
              <button type="button" disabled={busy} onClick={() => run()}>
                {busy ? "Working…" : "Re-analyze"}
              </button>
            </p>
          )}
          {result.warnings.map((w) => (
            <p key={w} className="lineup-analyzer-error">
              {w}
            </p>
          ))}
          <div className="lineup-analyzer-controls">
            <button type="button" className={tab === "ranked" ? "" : "secondary"} onClick={() => setTab("ranked")}>
              Ranked (top {result.rows.length})
            </button>
            {result.portfolio && (
              <>
                <button type="button" className={tab === "portfolio" ? "" : "secondary"} onClick={() => setTab("portfolio")}>
                  Portfolio ({result.portfolio.length})
                </button>
                <button type="button" onClick={() => download(`portfolio-week${week}.csv`, csvFor(result.portfolio ?? []))}>
                  Export DK upload CSV
                </button>
              </>
            )}
          </div>
          <LineupTable rows={shown} featureNames={features} />
        </section>
      )}
    </div>
  );
}
