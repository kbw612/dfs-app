import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchVegasLines, scrapeVegasLines } from "../api";
import type { VegasLineGame, VegasLinesSnapshot } from "../types";
import { gameEnvironmentTier, overUnderTier, tierClassName } from "./vegasLinesTiers";

interface VegasLinesViewProps {
  season: number;
  week: number;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

// null when either side is null or nothing actually moved -- so unchanged
// games render no delta line at all (see the "current line + delta only"
// display decision).
function formatDelta(label: string, initial: number | null, current: number | null): string | null {
  if (initial === null || current === null || initial === current) return null;
  const diff = current - initial;
  const sign = diff > 0 ? "+" : "";
  return `${label} ${initial} → ${current} (${sign}${diff})`;
}

type SortMode = "kickoff" | "over_under_desc" | "over_under_asc";

const MONTH_INDEX: Record<string, number> = {
  jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
  jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
};

// Best-effort parse of the scraped kickoff_label (e.g. "Wednesday, Sep 9th
// 8:20pm Eastern") into a sortable timestamp. kickoff_label is display text
// only -- never a real datetime (see backend/schemas/vegas_lines/
// vegas_lines.py's docstring) -- so this is heuristic: it extracts the
// month/day/time and assumes every game's label uses the same timezone
// ("Eastern" so far), which is all sorting needs (relative order within
// the week, not an absolute instant). `season` resolves the year --
// bumped a year for Jan/Feb kickoffs, since a late-season week can spill
// into the following calendar year. Returns null (sorts last) if the
// label is missing or doesn't match the expected shape.
function parseKickoffMillis(label: string | null, season: number): number | null {
  if (!label) return null;
  const match = label.match(/([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{1,2}):(\d{2})\s*([ap]m)/i);
  if (!match) return null;
  const [, monthName, dayStr, hourStr, minuteStr, ampm] = match;
  const month = MONTH_INDEX[monthName.slice(0, 3).toLowerCase()];
  if (month === undefined) return null;
  const day = Number(dayStr);
  let hour = Number(hourStr) % 12;
  if (ampm.toLowerCase() === "pm") hour += 12;
  const minute = Number(minuteStr);
  const year = month <= 1 ? season + 1 : season;
  const millis = new Date(year, month, day, hour, minute).getTime();
  return Number.isNaN(millis) ? null : millis;
}

// Stable sort (ties keep the scrape's own order) that always pushes
// unparseable/missing values to the end rather than mixing them in
// arbitrarily.
function sortGames(games: VegasLineGame[], mode: SortMode, season: number): VegasLineGame[] {
  return games
    .map((game, index) => ({ game, index }))
    .sort((a, b) => {
      if (mode === "over_under_desc" || mode === "over_under_asc") {
        const aOu = a.game.current.over_under;
        const bOu = b.game.current.over_under;
        if (aOu === null && bOu === null) return a.index - b.index;
        if (aOu === null) return 1;
        if (bOu === null) return -1;
        return mode === "over_under_desc" ? bOu - aOu : aOu - bOu;
      }
      const aMillis = parseKickoffMillis(a.game.kickoff_label, season);
      const bMillis = parseKickoffMillis(b.game.kickoff_label, season);
      if (aMillis === null && bMillis === null) return a.index - b.index;
      if (aMillis === null) return 1;
      if (bMillis === null) return -1;
      return aMillis - bMillis;
    })
    .map((entry) => entry.game);
}

export function VegasLinesView({ season, week }: VegasLinesViewProps) {
  const [data, setData] = useState<VegasLinesSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scraping, setScraping] = useState(false);
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("kickoff");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchVegasLines(season, week)
      .then((result) => setData(result))
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load Vegas Lines");
      })
      .finally(() => setLoading(false));
  }, [season, week]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleScrape() {
    setScraping(true);
    setScrapeMessage(null);
    try {
      const result = await scrapeVegasLines(season, week);
      const gameCount = result.snapshot.games.length;
      setScrapeMessage(
        result.messages.length > 0
          ? `Retrieved ${gameCount} game${gameCount === 1 ? "" : "s"} (${result.messages.length} note${
              result.messages.length === 1 ? "" : "s"
            } -- see below).`
          : `Retrieved ${gameCount} game${gameCount === 1 ? "" : "s"}.`
      );
      setData(result.snapshot);
      setError(null);
    } catch (err) {
      setScrapeMessage(err instanceof Error ? err.message : "Failed to retrieve Vegas Lines");
    } finally {
      setScraping(false);
    }
  }

  const isNotFound = error !== null && error.includes("No Vegas Lines scraped yet");

  const sortedGames = useMemo(() => sortGames(data?.games ?? [], sortMode, season), [data, sortMode, season]);

  return (
    <section className="ownership-section">
      <div className="player-pool-game-environment-header">
        <h2>Vegas Lines</h2>
        <button type="button" disabled={scraping} onClick={handleScrape}>
          {scraping ? "Retrieving…" : "Retrieve Vegas Lines"}
        </button>
      </div>
      {scrapeMessage && <p className="hint">{scrapeMessage}</p>}

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && (
        <p className="hint">
          No Vegas Lines scraped yet for season {season} week {week} -- click "Retrieve Vegas Lines" above.
        </p>
      )}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && data && (
        <>
          <p className="hint vegas-lines-timestamps">
            Last Updated: {formatTimestamp(data.current_scraped_at)} &middot; Initial scraped:{" "}
            {formatTimestamp(data.initial_scraped_at)}
          </p>

          {data.games.length > 0 && (
            <div className="chip-filter vegas-lines-sort">
              <span className="filter-label">Sort by</span>
              <div className="chip-row">
                <button
                  type="button"
                  className={`chip${sortMode === "kickoff" ? " selected" : ""}`}
                  aria-pressed={sortMode === "kickoff"}
                  onClick={() => setSortMode("kickoff")}
                >
                  Game time
                </button>
                <button
                  type="button"
                  className={`chip${sortMode === "over_under_desc" ? " selected" : ""}`}
                  aria-pressed={sortMode === "over_under_desc"}
                  onClick={() => setSortMode("over_under_desc")}
                >
                  O/U: High to low
                </button>
                <button
                  type="button"
                  className={`chip${sortMode === "over_under_asc" ? " selected" : ""}`}
                  aria-pressed={sortMode === "over_under_asc"}
                  onClick={() => setSortMode("over_under_asc")}
                >
                  O/U: Low to high
                </button>
              </div>
            </div>
          )}

          {sortedGames.length === 0 ? (
            <p className="hint">No games in this scrape.</p>
          ) : (
            <ul className="ownership-player-list pivot-card-list vegas-lines-list">
              {sortedGames.map((game, i) => {
                const deltas = [
                  formatDelta("O/U", game.initial.over_under, game.current.over_under),
                  formatDelta(game.away_name, game.initial.away_implied_total, game.current.away_implied_total),
                  formatDelta(game.home_name, game.initial.home_implied_total, game.current.home_implied_total),
                ].filter((d): d is string => d !== null);
                const awayTier = gameEnvironmentTier(game.current.away_implied_total, game.current.over_under);
                const homeTier = gameEnvironmentTier(game.current.home_implied_total, game.current.over_under);
                const ouTier = overUnderTier(game.current.over_under);

                return (
                  <li
                    key={game.game_key ?? `${game.away_name}-${game.home_name}-${i}`}
                    className="ownership-pivot-group vegas-lines-row"
                  >
                    {game.kickoff_label && <div className="vegas-lines-kickoff">{game.kickoff_label}</div>}
                    <div className="vegas-lines-matchup">
                      <span className={tierClassName(awayTier)}>
                        {game.away_name} ({game.current.away_implied_total ?? "-"})
                      </span>{" "}
                      at
                    </div>
                    <div className="vegas-lines-matchup">
                      <span className={tierClassName(homeTier)}>
                        {game.home_name} ({game.current.home_implied_total ?? "-"})
                      </span>
                    </div>
                    <div className="vegas-lines-ou">
                      <span className={tierClassName(ouTier)}>Over/Under {game.current.over_under ?? "-"}</span>
                    </div>
                    {deltas.length > 0 && <div className="vegas-lines-delta">{deltas.join(", ")}</div>}
                    {(game.away_team === null || game.home_team === null) && (
                      <div className="hint">Team name(s) unresolved -- won't apply to Game Environment</div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
