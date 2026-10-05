import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchGameRecaps, scrapeGameRecaps } from "../api";
import type { GameRecapWeekSnapshot } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

// Settings' Game Recaps panel -- walterfootball.com's own per-game recap
// text for a (season, week), displayed verbatim on the Game Logs / Game
// Logs Against tabs (see GameLogsView.tsx's recap mini-table). Mirrors
// WeeklyStatsUpload.tsx's own Scrape-button-plus-confirm pattern: always
// checks whether something's already saved first and always confirms
// before scraping, so an Add vs. Update (overwrite) distinction is stated
// up front rather than silently replacing a prior scrape.
//
// `urlMode` picks which of walterfootball.com's two page shapes to scrape:
// a numbered per-week URL ("nflreview2026_03.php", stable once that week is
// in the past) or the bare "current week" URL ("nflreview.php", which always
// points at whatever the site currently considers its latest week -- so it
// silently becomes next week's page once the site rolls over). The numbered
// page is right for any already-played week; the bare page is only right
// for the week the site currently has up, which is usually the most recent
// one but moves forward over time. Defaulting to "week_page" keeps the
// common case (re-scraping an already-played week) safe; the person flips
// to "current_page" when scraping the week the site hasn't numbered yet.
interface GameRecapUploadProps {
  season: number;
  week: number;
  onScraped: () => void;
}

export function GameRecapUpload({ season, week, onScraped }: GameRecapUploadProps) {
  const [scraping, setScraping] = useState(false);
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);
  const [urlMode, setUrlMode] = useState<"week_page" | "current_page">("week_page");
  const [confirm, setConfirm] = useState<{ message: ReactNode; onConfirm: () => void } | null>(null);

  async function handleScrape() {
    setScraping(true);
    setScrapeMessage(null);
    let alreadySaved = false;
    try {
      await fetchGameRecaps(season, week);
      alreadySaved = true;
    } catch {
      alreadySaved = false;
    }
    setScraping(false);
    setConfirm({
      message: (
        <p>
          {alreadySaved
            ? `Do you want to replace all Week ${week} game recaps?`
            : `Add game recaps for Week ${week}, ${season}?`}
        </p>
      ),
      onConfirm: performScrape,
    });
  }

  async function performScrape() {
    setConfirm(null);
    setScraping(true);
    try {
      const result = await scrapeGameRecaps(season, week, urlMode);
      const summary = `${result.snapshot.games.length} game${result.snapshot.games.length === 1 ? "" : "s"} saved`;
      setScrapeMessage(result.messages.length > 0 ? `${summary} -- ${result.messages.join(" · ")}` : summary);
      onScraped();
    } catch (err) {
      setScrapeMessage(err instanceof Error ? err.message : "Failed to scrape game recaps");
    } finally {
      setScraping(false);
    }
  }

  return (
    <div className="weekly-stats-upload">
      <div className="game-recap-url-mode">
        <label>
          <input
            type="radio"
            name="game-recap-url-mode"
            checked={urlMode === "week_page"}
            onChange={() => setUrlMode("week_page")}
          />
          Week page (e.g. nflreview2026_{String(week).padStart(2, "0")}.php) -- for an already-played week
        </label>
        <label>
          <input
            type="radio"
            name="game-recap-url-mode"
            checked={urlMode === "current_page"}
            onChange={() => setUrlMode("current_page")}
          />
          Current week page (nflreview.php) -- for whatever week the site currently has up
        </label>
      </div>
      <div className="weekly-stats-scrape-row">
        <button type="button" className="player-pool-save-button" disabled={scraping} onClick={handleScrape}>
          {scraping ? "Scraping…" : "Scrape Game Recaps"}
        </button>
        {scrapeMessage && <span className="hint">{scrapeMessage}</span>}
      </div>
      {confirm && (
        <ConfirmDialog
          message={confirm.message}
          confirmLabel="Scrape"
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}

interface GameRecapFileStatusProps {
  season: number;
  week: number;
  refreshToken: number;
}

// This (season, week)'s current saved-recap status, mirroring
// WeeklyStatsFileStatusList's display: when it was last scraped, which
// source URL it came from (so the person can see whether a prior scrape
// used the week page or the current page), and how many games are saved.
export function GameRecapFileStatus({ season, week, refreshToken }: GameRecapFileStatusProps) {
  const [snapshot, setSnapshot] = useState<GameRecapWeekSnapshot | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    fetchGameRecaps(season, week)
      .then((result) => {
        if (!cancelled) setSnapshot(result);
      })
      .catch(() => {
        if (!cancelled) setSnapshot(null);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, refreshToken]);

  if (snapshot === undefined) return null;

  return (
    <ul className="weekly-stats-file-status">
      <li>
        Week {week}, {season}:{" "}
        {snapshot
          ? `${snapshot.games.length} game${snapshot.games.length === 1 ? "" : "s"} saved (last scraped ${new Date(
              snapshot.scraped_at,
            ).toLocaleString()} from ${snapshot.source_url})`
          : "not scraped yet"}
      </li>
    </ul>
  );
}
