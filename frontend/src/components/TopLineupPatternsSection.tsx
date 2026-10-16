import { useEffect, useState } from "react";
import { fetchTopLineupPatterns } from "../api";
import type { TopLineupPatternsResult } from "../types";
import { CollapsibleHint } from "./CollapsibleHint";

// Weeks analyzed and per-week lineup cap -- fixed, per the request "weeks 1-4,
// top 1000 lineups". Contests with fewer entries just contribute all of them.
const PATTERN_WEEKS = [1, 2, 3, 4];
const PATTERN_TOP_N = 1000;

interface TopLineupPatternsSectionProps {
  season: number;
  platform: string;
  contest: string;
}

function formatPct(value: number | null): string {
  return value === null ? "-" : `${value.toFixed(1)}%`;
}

function formatSalary(value: number | null): string {
  return value === null ? "-" : `$${Math.round(value).toLocaleString()}`;
}

// Generic stack/flex/DST/salary patterns used by the top finishing lineups
// of past contests -- see backend/services/lineup_scenarios/
// top_lineup_patterns.py for exactly what each category counts.
export function TopLineupPatternsSection({ season, platform, contest }: TopLineupPatternsSectionProps) {
  const [result, setResult] = useState<TopLineupPatternsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTopLineupPatterns(season, PATTERN_WEEKS, platform, contest, PATTERN_TOP_N)
      .then((data) => {
        if (!cancelled) setResult(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setResult(null);
        setError(err instanceof Error ? err.message : "Failed to load top lineup patterns");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [season, platform, contest]);

  return (
    <section className="top-lineup-patterns">
      <h3>Top Lineup Patterns (Weeks {PATTERN_WEEKS[0]}-{PATTERN_WEEKS[PATTERN_WEEKS.length - 1]})</h3>
      <CollapsibleHint
        title="About this section"
        items={[
          `Position-structure patterns (no team names) across the top ${PATTERN_TOP_N} finishing lineups of each week's ${contest} contest, from the uploaded contest standings and DK salary files.`,
          "Count is how many lineups contain the pattern; % is of all lineups analyzed. W1-W4 break the count out by week. Other-game and other-team stacks can appear more than once in a lineup, so those categories don't sum to 100%.",
          "Avg Own % is the contest's actual %Drafted (summed across roster slots) averaged over the pattern's own players, then averaged across lineups. Avg Salary is the combined salary of those same players (the stack's salary block). Avg Pts is the average lineup score.",
          "A pattern's players are the ones it describes: QB plus stacked teammates for QB stacks, the bring-back players for bring-backs, DST plus the matching players for DST patterns, the whole lineup for unused salary.",
          `Stars are non-DST players priced $8,000+; punts are $4,000 or less. Each category shows its most frequent patterns.`,
        ]}
      />

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && <p className="hint lineup-scenarios-error">{error}</p>}

      {!loading && result && (
        <>
          <p className="hint">
            {result.lineups_analyzed.toLocaleString()} lineups analyzed (
            {result.weeks_included.map((w) => `W${w}: ${result.lineups_by_week[String(w)] ?? 0}`).join(", ")})
            {result.lineups_skipped > 0 &&
              `; ${result.lineups_skipped} skipped because a player didn't match the salary file`}
            {result.weeks_missing.length > 0 &&
              `; no standings or salary file for week${result.weeks_missing.length === 1 ? "" : "s"} ${result.weeks_missing.join(", ")}`}
            .
          </p>
          {result.categories.map((category) => (
            <div className="top-lineup-patterns-category" key={category.key}>
              <h4>{category.label}</h4>
              <p className="hint">
                {category.description}
                {category.distinct_patterns > category.patterns.length &&
                  ` Showing the top ${category.patterns.length} of ${category.distinct_patterns} patterns.`}
              </p>
              <table className="lineup-scenarios-table top-lineup-patterns-table">
                <thead>
                  <tr>
                    <th>Pattern</th>
                    <th>Count</th>
                    <th>%</th>
                    {result.weeks_included.map((w) => (
                      <th key={w}>W{w}</th>
                    ))}
                    <th>Avg Own %</th>
                    <th>Avg Salary</th>
                    <th>Avg Pts</th>
                  </tr>
                </thead>
                <tbody>
                  {category.patterns.map((p) => (
                    <tr key={p.pattern}>
                      <td>{p.pattern}</td>
                      <td>{p.count}</td>
                      <td>{formatPct(p.pct_of_lineups)}</td>
                      {result.weeks_included.map((w) => (
                        <td key={w}>{p.by_week[String(w)] ?? 0}</td>
                      ))}
                      <td>{formatPct(p.avg_ownership_pct)}</td>
                      <td>{formatSalary(p.avg_salary_total)}</td>
                      <td>{p.avg_points.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}
    </section>
  );
}
