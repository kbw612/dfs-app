import { Fragment, useEffect, useMemo, useState } from "react";
import {
  addTrackerContest,
  deleteTrackerContest,
  deleteTrackerEntry,
  fetchContestTracker,
  putTrackerEntry,
  renameTrackerContest,
} from "../api";
import type { ContestTrackerResult, TrackerEntry, TrackerTopFinish } from "../types";

interface ContestTrackerViewProps {
  season: number;
}

const WEEKS = Array.from({ length: 19 }, (_, i) => i + 1);

function money(n: number): string {
  return `$${n.toFixed(2)}`;
}

function signedMoney(n: number): string {
  return `${n < 0 ? "-" : "+"}$${Math.abs(n).toFixed(2)}`;
}

function signClass(n: number): string {
  return n < 0 ? "tracker-neg" : n > 0 ? "tracker-pos" : "";
}

function pct(n: number | null): string {
  return n === null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function finishesToText(finishes: TrackerTopFinish[]): string {
  return finishes.map((f) => `${f.place} / $${f.payout}`).join("\n");
}

// "151 / $30" per line -> [{place:151, payout:30}]; null if any line is malformed.
function parseFinishes(text: string): TrackerTopFinish[] | null {
  const out: TrackerTopFinish[] = [];
  for (const line of text.split("\n").map((l) => l.trim()).filter(Boolean)) {
    const m = line.match(/^(\d+)\s*\/\s*\$?(\d+(?:\.\d+)?)$/);
    if (!m) return null;
    out.push({ place: Number(m[1]), payout: Number(m[2]) });
  }
  return out;
}

// The left cell of each contest: name plus its Entered / Won / ROI / Played
// figures, so the summary is always visible without scrolling the weeks.
function SummaryCell(props: {
  name: string;
  cost: number;
  won: number;
  roi: number | null;
  played: string;
  playedLabel?: string;
}) {
  return (
    <td className="tracker-summary" rowSpan={2}>
      <div className="tracker-summary-name">{props.name}</div>
      <div className="tracker-summary-stats">
        <span>
          Entered <b>{money(props.cost)}</b>
        </span>
        <span>
          Won <b>{money(props.won)}</b>
        </span>
        <span>
          ROI <b className={props.roi === null ? "" : signClass(props.roi)}>{pct(props.roi)}</b>
        </span>
        <span>
          {props.playedLabel ?? "Played"}{" "}
          <b>{props.playedLabel ? props.played.replace(/^net /, "") : props.played}</b>
        </span>
      </div>
    </td>
  );
}

export function ContestTrackerView({ season: headerSeason }: ContestTrackerViewProps) {
  const [season, setSeason] = useState(headerSeason);
  const [data, setData] = useState<ContestTrackerResult | null>(null);
  const [selected, setSelected] = useState<{ contestId: string; week: number } | null>(null);
  const [cost, setCost] = useState("");
  const [won, setWon] = useState("");
  const [finishes, setFinishes] = useState("");
  const [newName, setNewName] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelected(null);
    fetchContestTracker(season)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, [season]);

  const entryFor = (contestId: string, week: number): TrackerEntry | undefined =>
    data?.contests.find((c) => c.id === contestId)?.entries.find((e) => e.week === week);

  const run = async (action: Promise<ContestTrackerResult>) => {
    try {
      setData(await action);
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  };

  const select = (contestId: string, week: number) => {
    const e = entryFor(contestId, week);
    setSelected({ contestId, week });
    setCost(e ? String(e.cost) : "");
    setWon(e ? String(e.won) : "");
    setFinishes(e ? finishesToText(e.top_finishes) : "");
    setError(null);
  };

  // Saves when a field loses focus. A cost is required to create an entry; an
  // empty cost on an existing entry is left alone (use "Mark not played").
  const save = () => {
    if (!selected || cost.trim() === "") return;
    const costN = Number(cost);
    const wonN = won.trim() === "" ? 0 : Number(won);
    const parsed = parseFinishes(finishes);
    if (!(costN > 0) || !(wonN >= 0) || Number.isNaN(wonN)) {
      setError("Cost must be more than 0 and won can't be negative.");
      return;
    }
    if (parsed === null) {
      setError("Top finishes: one per line as place / $payout, e.g. 151 / $30.");
      return;
    }
    const existing = entryFor(selected.contestId, selected.week);
    if (
      existing &&
      existing.cost === costN &&
      existing.won === wonN &&
      JSON.stringify(existing.top_finishes) === JSON.stringify(parsed)
    ) {
      return;
    }
    run(putTrackerEntry(season, { contest_id: selected.contestId, week: selected.week, cost: costN, won: wonN, top_finishes: parsed }));
  };

  const selectedContest = useMemo(
    () => data?.contests.find((c) => c.id === selected?.contestId) ?? null,
    [data, selected]
  );
  const selectedEntry = selected ? entryFor(selected.contestId, selected.week) : undefined;
  const elapsed = data?.weeks_elapsed ?? 0;
  // Through the next week to play, unless the full season is requested.
  const weeks = showAll ? WEEKS : WEEKS.slice(0, Math.min(WEEKS.length, Math.max(elapsed + 1, 8)));

  return (
    <div className="contest-tracker">
      <h2>Results Tracker</h2>
      <div className="tracker-controls">
        <label>
          Season{" "}
          <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value) || headerSeason)} />
        </label>
        <span className="tracker-hint">Cells show net profit (won minus cost). A dash is a week not played.</span>
        <button type="button" className="secondary" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show fewer weeks" : "Show all 19 weeks"}
        </button>
        <span className="tracker-spacer" />
        <input
          placeholder="New contest name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && newName.trim() && (run(addTrackerContest(season, newName.trim())), setNewName(""))}
        />
        <button
          type="button"
          disabled={!newName.trim()}
          onClick={() => {
            run(addTrackerContest(season, newName.trim()));
            setNewName("");
          }}
        >
          Add contest
        </button>
      </div>
      {error && <p className="tracker-error">{error}</p>}

      {data && (
        <div className="tracker-table-wrap">
          <table className="tracker-grid">
            <thead>
              <tr>
                <th className="tracker-left">Contest</th>
                <th className="tracker-left"></th>
                {weeks.map((w) => (
                  <th key={w}>W{w}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.contests.map((c) => (
                <Fragment key={c.id}>
                  <tr>
                    <SummaryCell name={c.name} cost={c.cost} won={c.won} roi={c.roi_pct} played={`${c.played} / ${elapsed}`} />
                    <td className="tracker-rowlabel">Entered</td>
                    {weeks.map((w) => {
                      const e = c.entries.find((x) => x.week === w);
                      const isSel = selected?.contestId === c.id && selected.week === w;
                      return (
                        <td
                          key={w}
                          className={`tracker-cell ${e ? "" : "tracker-skip"}${isSel ? " tracker-selected-top" : ""}`}
                          onClick={() => select(c.id, w)}
                        >
                          {e ? money(e.cost) : w <= elapsed ? "—" : "+"}
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td className="tracker-rowlabel">Net</td>
                    {weeks.map((w) => {
                      const e = c.entries.find((x) => x.week === w);
                      const isSel = selected?.contestId === c.id && selected.week === w;
                      const net = e ? e.won - e.cost : 0;
                      return (
                        <td
                          key={w}
                          className={`tracker-cell ${e ? signClass(net) : "tracker-skip"}${isSel ? " tracker-selected-bottom" : ""}`}
                          onClick={() => select(c.id, w)}
                        >
                          {e ? signedMoney(net) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                </Fragment>
              ))}
              {data.contests.length === 0 && (
                <tr>
                  <td className="tracker-left" colSpan={weeks.length + 2}>
                    No contests yet. Add one above (for example, a contest type you enter every week).
                  </td>
                </tr>
              )}
              {data.contests.length > 0 && (
                <>
                  <tr className="tracker-total">
                    <SummaryCell
                      name="All contests"
                      cost={data.total_cost}
                      won={data.total_won}
                      roi={data.total_roi_pct}
                      played={`net ${signedMoney(data.net)}`}
                      playedLabel="Net"
                    />
                    <td className="tracker-rowlabel">Entered</td>
                    {weeks.map((w) => {
                      const spent = data.contests.reduce((sum, c) => sum + (c.entries.find((x) => x.week === w)?.cost ?? 0), 0);
                      return (
                        <td key={w} className={spent > 0 ? "" : "tracker-skip"}>
                          {spent > 0 ? money(spent) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                  <tr className="tracker-total">
                    <td className="tracker-rowlabel">Net</td>
                    {weeks.map((w) => {
                      const n = data.week_net[String(w)];
                      return (
                        <td key={w} className={n === undefined ? "tracker-skip" : signClass(n)}>
                          {n === undefined ? "—" : signedMoney(n)}
                        </td>
                      );
                    })}
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && selectedContest && (
        <div className="tracker-detail">
          <div className="tracker-detail-title">
            {selectedContest.name}, week {selected.week}
            {!selectedEntry && <span className="tracker-hint"> (not played)</span>}
          </div>
          <div className="tracker-controls">
            <label>
              Cost ($)
              <input value={cost} onChange={(e) => setCost(e.target.value)} onBlur={save} />
            </label>
            <label>
              Won ($)
              <input value={won} onChange={(e) => setWon(e.target.value)} onBlur={save} />
            </label>
            <label>
              Top finishes (place / $payout, one per line)
              <textarea rows={2} value={finishes} onChange={(e) => setFinishes(e.target.value)} onBlur={save} />
            </label>
            {selectedEntry && (
              <button
                type="button"
                onClick={() => {
                  run(deleteTrackerEntry(season, selected.contestId, selected.week));
                  setCost("");
                  setWon("");
                  setFinishes("");
                }}
              >
                Mark not played
              </button>
            )}
          </div>
          <div className="tracker-controls">
            <button
              type="button"
              className="secondary"
              onClick={() => {
                const name = window.prompt("Rename contest", selectedContest.name);
                if (name && name.trim()) run(renameTrackerContest(season, selectedContest.id, name.trim()));
              }}
            >
              Rename contest
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                if (window.confirm(`Delete "${selectedContest.name}" and all its entries?`)) {
                  run(deleteTrackerContest(season, selectedContest.id));
                  setSelected(null);
                }
              }}
            >
              Delete contest
            </button>
            <span className="tracker-hint">Changes save when you leave a field.</span>
          </div>
        </div>
      )}
    </div>
  );
}
