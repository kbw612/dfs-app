import { useEffect, useRef, useState } from "react";
import { fetchGameLogsSummary } from "../api";
import type { GameLogsSummaryResult } from "../types";
import { CollapsibleHint } from "./CollapsibleHint";
import { QbPassingPanel } from "./QbPassingPanel";
import { RbReceivingPanel } from "./RbReceivingPanel";
import { RbRushingPanel } from "./RbRushingPanel";

// Game Logs Summary -- slate-wide roll-ups over the last "Weeks to show"
// completed weeks. Today that is the QB passing-yards panel; the summary
// lines are always visible and the QB table expands/collapses (see
// QbPassingPanel.tsx). season/week/platform/contest come from the shared
// header control, same as every other weekly tab.
interface GameLogsSummaryViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

// Same debounce as Game Previews' own "Weeks to show" input.
const WINDOW_WEEKS_DEBOUNCE_MS = 800;

export function GameLogsSummaryView({ season, week, platform, contest }: GameLogsSummaryViewProps) {
  const [windowWeeksInput, setWindowWeeksInput] = useState("5");
  const [windowWeeks, setWindowWeeks] = useState(5);
  const windowDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [result, setResult] = useState<GameLogsSummaryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchGameLogsSummary(season, week, windowWeeks, platform, contest)
      .then((data) => {
        if (!cancelled) setResult(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setResult(null);
        setError(err instanceof Error ? err.message : "Failed to load Game Logs Summary");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, windowWeeks, platform, contest]);

  useEffect(() => {
    const timer = windowDebounce;
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function commitWindowWeeks(value: string) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) {
      setWindowWeeks(Math.floor(parsed));
    } else {
      setWindowWeeksInput(String(windowWeeks));
    }
  }

  function handleWindowWeeksChange(value: string) {
    setWindowWeeksInput(value);
    if (windowDebounce.current) clearTimeout(windowDebounce.current);
    windowDebounce.current = setTimeout(() => {
      windowDebounce.current = null;
      commitWindowWeeks(value);
    }, WINDOW_WEEKS_DEBOUNCE_MS);
  }

  function handleWindowWeeksBlur() {
    if (windowDebounce.current) {
      clearTimeout(windowDebounce.current);
      windowDebounce.current = null;
    }
    commitWindowWeeks(windowWeeksInput);
  }

  return (
    <>
      <CollapsibleHint
        items={[
          `Slate-wide roll-ups over the last ${windowWeeks} completed week${windowWeeks === 1 ? "" : "s"} before week ${week}, narrowed to this contest's own slate.`,
          "QB passing yards: games of 300+ and 265-299 passing yards by QBs, and the same games grouped by the defense that allowed them. The 265-299 counts exclude the 300+ games.",
          "RB rushing yards: games of 100+ and 75-99 rushing yards by RBs (fullbacks included), and the games defenses have allowed. A defense's games add up all of a team's RBs; each back's own yards are listed beside the total.",
          "TD columns: games with 3+ passing TDs (QBs) or 1+ rushing/receiving TDs (RBs), beside the same games defenses have allowed.",
          "RB receiving: games of 50+ receiving yards by RBs, and the games defenses have allowed to a team's RBs combined.",
          "The table lists QBs playing this week who have a 265+ game of their own, or who are their team's primary QB facing a defense that has allowed one. Opp D allowed 265+ includes 300+ games.",
        ]}
      />

      <div className="filters">
        <label className="game-logs-lookback-field">
          Weeks to show
          <input
            type="number"
            min={1}
            max={17}
            value={windowWeeksInput}
            onChange={(e) => handleWindowWeeksChange(e.target.value)}
            onBlur={handleWindowWeeksBlur}
          />
        </label>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && <p className="error">{error}</p>}
      {!loading &&
        !error &&
        result !== null &&
        result.qb_passing === null &&
        result.rb_rushing === null &&
        result.rb_receiving === null && (
        <p className="hint">
          No QB or RB stat lines in the last {windowWeeks} week{windowWeeks === 1 ? "" : "s"} before week {week} yet.
        </p>
      )}
      {!loading && !error && result?.qb_passing && <QbPassingPanel data={result.qb_passing} />}
      {!loading && !error && result?.rb_rushing && <RbRushingPanel data={result.rb_rushing} />}
      {!loading && !error && result?.rb_receiving && <RbReceivingPanel data={result.rb_receiving} />}
    </>
  );
}
