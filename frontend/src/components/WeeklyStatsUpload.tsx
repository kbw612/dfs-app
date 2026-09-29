import { Fragment, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchWeeklyStatsFileInfo, scrapeWeeklyStats } from "../api";
import type { WeeklyStatsFileStatus } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

// Settings' Weekly Stats panel -- the 5 FantasyData exports (QB/RB/WR/TE/DST)
// that feed DK Players' "Calc Week N Points & Fantasy Data" action (see
// backend/services/dk_players/weekly_stats_loader.py for the column shape
// each one has). Not platform-scoped -- these are league-wide stats, not
// tied to a DK contest. Scrape is the only way these files get populated
// -- there used to also be a manual per-position CSV upload here as a
// backup, removed since the person always uses Scrape.  `onUploaded` lets
// Settings refresh the combined status list below after a scrape succeeds.
interface WeeklyStatsUploadProps {
  season: number;
  week: number;
  onUploaded: () => void;
}

export function WeeklyStatsUpload({ season, week, onUploaded }: WeeklyStatsUploadProps) {
  const [scraping, setScraping] = useState(false);
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);
  // Pending confirm-popover, if any -- replaces window.confirm (a blocking
  // browser dialog, not part of the app's own UI) with an in-page modal.
  // Set this to show it; the dialog's own Confirm/Cancel buttons resolve
  // or clear it.
  const [confirm, setConfirm] = useState<{ message: ReactNode; onConfirm: () => void } | null>(null);

  // Scrapes all 4 positions from FantasyData in one action. Always checks
  // file-info first and always confirms before scraping -- not just when
  // something would be overwritten -- so the season/week being scraped and
  // each position's Add (season file has no rows for this week yet) vs.
  // Update (this week's rows already exist and will be replaced) status are
  // both stated up front rather than only surfacing a warning in the
  // overwrite case. scrapeWeeklyStats itself always overwrites an existing
  // week's rows, so this is the only place that distinction is shown.
  async function handleScrape() {
    setScraping(true);
    setScrapeMessage(null);
    try {
      const info = await fetchWeeklyStatsFileInfo(season, week);
      setScraping(false);
      setConfirm({
        message: (
          <>
            <p>
              Scrape Week {week}, {season} stats?
            </p>
            <div className="confirm-dialog-grid">
              {info.files.map((f) => (
                <Fragment key={f.position}>
                  <span>{f.position}:</span>
                  <span>{f.week_has_data ? "Update" : "Add"}</span>
                </Fragment>
              ))}
            </div>
          </>
        ),
        onConfirm: performScrape,
      });
    } catch (err) {
      setScrapeMessage(err instanceof Error ? err.message : "Failed to scrape weekly stats");
      setScraping(false);
    }
  }

  async function performScrape() {
    setConfirm(null);
    setScraping(true);
    try {
      const result = await scrapeWeeklyStats(season, week);
      const summary = result.results
        .map((r) => (r.error ? `${r.position}: ${r.error}` : `${r.position}: ${r.row_count} rows`))
        .join(" · ");
      setScrapeMessage(summary);
      onUploaded();
    } catch (err) {
      setScrapeMessage(err instanceof Error ? err.message : "Failed to scrape weekly stats");
    } finally {
      setScraping(false);
    }
  }

  return (
    <div className="weekly-stats-upload">
      <div className="weekly-stats-scrape-row">
        <button type="button" className="player-pool-save-button" disabled={scraping} onClick={handleScrape}>
          {scraping ? "Scraping…" : "Scrape Weekly Stats (QB/RB/WR/TE/DST)"}
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

interface WeeklyStatsFileStatusListProps {
  season: number;
  week: number;
  refreshToken: number;
}

// All 4 positions' current season-file status, plus whether the
// currently-selected week specifically has been saved into each one yet
// -- each position's file (e.g. "FantasyData_QBs.csv") grows across the
// season rather than being one file per week, so "modified" reflects the
// last save to ANY week, not necessarily this one.
export function WeeklyStatsFileStatusList({ season, week, refreshToken }: WeeklyStatsFileStatusListProps) {
  const [files, setFiles] = useState<WeeklyStatsFileStatus[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWeeklyStatsFileInfo(season, week)
      .then((result) => {
        if (!cancelled) setFiles(result.files);
      })
      .catch(() => {
        if (!cancelled) setFiles(null);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, refreshToken]);

  if (!files) return null;

  return (
    <ul className="weekly-stats-file-status">
      {files.map((f) => (
        <li key={f.position}>
          {f.position}:{" "}
          {f.filename
            ? `${f.filename} (last saved ${new Date(f.uploaded_at as string).toLocaleString()}) -- Week ${week}: ${
                f.week_has_data ? "saved" : "not yet saved"
              }`
            : "not uploaded"}
        </li>
      ))}
    </ul>
  );
}
