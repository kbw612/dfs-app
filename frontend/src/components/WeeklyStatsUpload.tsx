import { useEffect, useState } from "react";
import { fetchWeeklyStatsFileInfo, importWeeklyStatsCsv, scrapeWeeklyStats } from "../api";
import type { WeeklyStatsFileStatus, WeeklyStatsPosition } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";

// Settings' Weekly Stats panel -- the 4 FantasyData exports (QB/RB/WR/TE)
// that feed DK Players' "Update Week N Points" action (see
// backend/services/dk_players/weekly_stats_loader.py for the column shape
// each one has). Not platform-scoped -- these are league-wide stats, not
// tied to a DK contest. `onUploaded` lets Settings refresh the combined
// status list below after any one of the 4 uploads (or the scrape below)
// succeeds.
interface WeeklyStatsUploadProps {
  season: number;
  week: number;
  onUploaded: () => void;
}

const POSITIONS: WeeklyStatsPosition[] = ["QB", "RB", "WR", "TE"];

export function WeeklyStatsUpload({ season, week, onUploaded }: WeeklyStatsUploadProps) {
  const [files, setFiles] = useState<Record<WeeklyStatsPosition, File | null>>({ QB: null, RB: null, WR: null, TE: null });
  const [uploading, setUploading] = useState<WeeklyStatsPosition | null>(null);
  const [messages, setMessages] = useState<Record<WeeklyStatsPosition, string | null>>({
    QB: null,
    RB: null,
    WR: null,
    TE: null,
  });
  const [scraping, setScraping] = useState(false);
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);
  // Pending confirm-popover, if any -- replaces window.confirm (a blocking
  // browser dialog, not part of the app's own UI) with an in-page modal.
  // Set this to show it; the dialog's own Confirm/Cancel buttons resolve
  // or clear it.
  const [confirm, setConfirm] = useState<{ message: string; onConfirm: () => void } | null>(null);

  async function handleUpload(position: WeeklyStatsPosition) {
    const file = files[position];
    if (!file) return;
    setUploading(position);
    setMessages((prev) => ({ ...prev, [position]: null }));
    try {
      // This position's season file may already have `week`'s rows in it
      // (e.g. re-uploading a corrected file, or after a scrape) --
      // importWeeklyStatsCsv always overwrites just that week's rows, so
      // confirm first rather than silently replacing them.
      const info = await fetchWeeklyStatsFileInfo(season, week);
      const status = info.files.find((f) => f.position === position);
      if (status?.week_has_data) {
        setUploading(null);
        setConfirm({
          message: `Week ${week} already has saved ${position} stats -- uploading will overwrite them. Continue?`,
          onConfirm: () => performUpload(position, file),
        });
        return;
      }
      await performUpload(position, file);
    } catch (err) {
      setMessages((prev) => ({
        ...prev,
        [position]: err instanceof Error ? err.message : `Failed to upload ${position} stats`,
      }));
      setUploading(null);
    }
  }

  async function performUpload(position: WeeklyStatsPosition, file: File) {
    setConfirm(null);
    setUploading(position);
    try {
      const result = await importWeeklyStatsCsv(season, week, position, file);
      setMessages((prev) => ({ ...prev, [position]: `Loaded ${result.row_count} rows` }));
      setFiles((prev) => ({ ...prev, [position]: null }));
      onUploaded();
    } catch (err) {
      setMessages((prev) => ({
        ...prev,
        [position]: err instanceof Error ? err.message : `Failed to upload ${position} stats`,
      }));
    } finally {
      setUploading(null);
    }
  }

  // Scrapes all 4 positions from FantasyData in one action. Checks
  // file-info first so an existing week's data isn't silently clobbered --
  // scrapeWeeklyStats itself always overwrites, same as a manual upload,
  // so the confirmation has to happen here rather than server-side.
  async function handleScrape() {
    setScraping(true);
    setScrapeMessage(null);
    try {
      const info = await fetchWeeklyStatsFileInfo(season, week);
      const existing = info.files.filter((f) => f.week_has_data).map((f) => f.position);
      if (existing.length > 0) {
        setScraping(false);
        setConfirm({
          message: `Week ${week} already has saved stats for ${existing.join(", ")} -- scraping will overwrite ${
            existing.length === 1 ? "it" : "them"
          }. Continue?`,
          onConfirm: performScrape,
        });
        return;
      }
      await performScrape();
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
          {scraping ? "Scraping…" : "Scrape Weekly Stats (QB/RB/WR/TE)"}
        </button>
        {scrapeMessage && <span className="hint">{scrapeMessage}</span>}
      </div>
      {POSITIONS.map((position) => (
        <div key={position} className="player-pool-upload weekly-stats-upload-row">
          <span className="weekly-stats-position-label">{position}</span>
          <label className="player-pool-upload-label">
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setFiles((prev) => ({ ...prev, [position]: e.target.files?.[0] ?? null }))}
            />
          </label>
          <button
            type="button"
            className="player-pool-save-button"
            disabled={!files[position] || uploading === position}
            onClick={() => handleUpload(position)}
          >
            {uploading === position ? "Uploading…" : "Upload"}
          </button>
          {messages[position] && <span className="hint">{messages[position]}</span>}
        </div>
      ))}
      {confirm && (
        <ConfirmDialog
          message={confirm.message}
          confirmLabel="Overwrite"
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
