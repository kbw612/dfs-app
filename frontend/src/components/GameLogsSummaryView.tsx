import { useEffect, useMemo, useRef, useState } from "react";
import { fetchFptsPanels, fetchGameLogsSummary } from "../api";
import type { FptsPanelsResult, GameLogsSummaryResult } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { CollapsibleHint } from "./CollapsibleHint";
import { ContestFileNotice } from "./ContestFileNotice";
import { QbPassingPanel } from "./QbPassingPanel";
import { PositionFptsPanel } from "./PositionFptsPanel";
import { PositionMultiplierPanel } from "./PositionMultiplierPanel";
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

// Keeps only the rows whose player's team passes `keep`, and drops any "best
// setups" entry for a player who is no longer in the table. The slate-wide
// totals in each summary line stay as the backend computed them.
function filterPanel<T extends { rows: { name: string; team: string }[]; best_setups: { name: string }[] }>(
  panel: T | null,
  keep: (team: string) => boolean
): T | null {
  if (panel === null) return null;
  const rows = panel.rows.filter((row) => keep(row.team));
  const names = new Set(rows.map((row) => row.name));
  return { ...panel, rows, best_setups: panel.best_setups.filter((s) => names.has(s.name)) };
}

// Same debounce as Game Previews' own "Weeks to show" input.
const WINDOW_WEEKS_DEBOUNCE_MS = 800;

export function GameLogsSummaryView({ season, week, platform, contest }: GameLogsSummaryViewProps) {
  const [windowWeeksInput, setWindowWeeksInput] = useState("5");
  const [windowWeeks, setWindowWeeks] = useState(5);
  const windowDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Game: single-select, same as Game Logs / Game Logs Against -- keeps the
  // players of that matchup's two teams. Team: multi-select, independent of
  // Game. Both filter the tables by the player's own team.
  const [selectedGame, setSelectedGame] = useState<string | null>(null);
  const [selectedTeams, setSelectedTeams] = useState<Set<string>>(new Set());

  const [result, setResult] = useState<GameLogsSummaryResult | null>(null);
  const [fpts, setFpts] = useState<FptsPanelsResult | null>(null);
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

  // FPTS panels come finished from the backend, which applies the Game/Team
  // chips itself.
  useEffect(() => {
    let cancelled = false;
    fetchFptsPanels(season, week, windowWeeks, platform, contest, selectedGame, [...selectedTeams])
      .then((data) => {
        if (!cancelled) setFpts(data);
      })
      .catch(() => {
        if (!cancelled) setFpts(null);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, windowWeeks, platform, contest, selectedGame, selectedTeams]);

  useEffect(() => {
    const timer = windowDebounce;
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const games = result?.games ?? [];
  const gameByKey = useMemo(() => new Map(games.map((g) => [g.key, g])), [games]);
  // Built from every game on the slate, not narrowed by the selected Game.
  const teamOptions = useMemo(() => [...new Set(games.flatMap((g) => g.teams))].sort(), [games]);

  // Reset a stale Game selection when the slate changes under it.
  useEffect(() => {
    setSelectedGame(null);
  }, [season, week, contest]);

  const filtered = useMemo(() => {
    const gameTeams = selectedGame ? (gameByKey.get(selectedGame)?.teams ?? []) : null;
    const keep = (team: string) =>
      (gameTeams === null || gameTeams.includes(team)) && (selectedTeams.size === 0 || selectedTeams.has(team));
    return {
      qb_passing: filterPanel(result?.qb_passing ?? null, keep),
      rb_rushing: filterPanel(result?.rb_rushing ?? null, keep),
      rb_receiving: filterPanel(result?.rb_receiving ?? null, keep),
      qb_multipliers: filterPanel(result?.qb_multipliers ?? null, keep),
      rb_multipliers: filterPanel(result?.rb_multipliers ?? null, keep),
      wr_multipliers: filterPanel(result?.wr_multipliers ?? null, keep),
      te_multipliers: filterPanel(result?.te_multipliers ?? null, keep),
    };
  }, [result, selectedGame, selectedTeams, gameByKey]);

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
          "FPTS panels (QB, RB, WR, TE, DST): player games in the Elite and Strong fantasy-point bands for the position, and the games each opponent has allowed. DST panels list the opposing offense.",
          "Salary multipliers (QB, RB, WR, TE panels): player games of 4x+, 3-3.99x and non-TD 2.5x+ (fantasy points per $1,000 of salary), and the games defenses have allowed at that position.",
          "The table lists QBs playing this week who have a 265+ game of their own, or who are their team's primary QB facing a defense that has allowed one. Opp D allowed 265+ includes 300+ games.",
        ]}
      />

      <ContestFileNotice missing={result?.contest_salary_file_missing ?? false} contest={contest} week={week} />

      <div className="filters">
        <div className="chip-filter">
          <span className="filter-label">Game</span>
          <div className="chip-row">
            <button
              type="button"
              className={`chip${selectedGame === null ? " selected" : ""}`}
              aria-pressed={selectedGame === null}
              onClick={() => setSelectedGame(null)}
            >
              All
            </button>
            {games.map((g) => (
              <button
                key={g.key}
                type="button"
                className={`chip${selectedGame === g.key ? " selected" : ""}`}
                aria-pressed={selectedGame === g.key}
                onClick={() => setSelectedGame((current) => (current === g.key ? null : g.key))}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>
        <ChipMultiSelect label="Team" options={teamOptions} selected={selectedTeams} onChange={setSelectedTeams} />
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
      {/* FPTS panels, in QB, RB, WR, TE, DST order. */}
      {!loading && !error && fpts?.qb && <PositionFptsPanel data={fpts.qb} />}
      {!loading && !error && fpts?.rb && <PositionFptsPanel data={fpts.rb} />}
      {!loading && !error && fpts?.wr && <PositionFptsPanel data={fpts.wr} />}
      {!loading && !error && fpts?.te && <PositionFptsPanel data={fpts.te} />}
      {!loading && !error && fpts?.dst && <PositionFptsPanel data={fpts.dst} />}
      {!loading &&
        !error &&
        result !== null &&
        result.qb_passing === null &&
        result.rb_rushing === null &&
        result.rb_receiving === null &&
        result.qb_multipliers === null &&
        result.rb_multipliers === null &&
        result.wr_multipliers === null &&
        result.te_multipliers === null && (
        <p className="hint">
          No QB or RB stat lines in the last {windowWeeks} week{windowWeeks === 1 ? "" : "s"} before week {week} yet.
        </p>
      )}
      {!loading && !error && filtered.qb_passing && <QbPassingPanel data={filtered.qb_passing} />}
      {!loading && !error && filtered.rb_rushing && <RbRushingPanel data={filtered.rb_rushing} />}
      {!loading && !error && filtered.rb_receiving && <RbReceivingPanel data={filtered.rb_receiving} />}
      {/* Multiplier panels, in QB, RB, WR, TE order. */}
      {!loading && !error && filtered.qb_multipliers && <PositionMultiplierPanel data={filtered.qb_multipliers} />}
      {!loading && !error && filtered.rb_multipliers && <PositionMultiplierPanel data={filtered.rb_multipliers} />}
      {!loading && !error && filtered.wr_multipliers && <PositionMultiplierPanel data={filtered.wr_multipliers} />}
      {!loading && !error && filtered.te_multipliers && <PositionMultiplierPanel data={filtered.te_multipliers} />}
    </>
  );
}
