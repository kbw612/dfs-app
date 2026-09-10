import { useEffect, useState } from "react";
import { fetchWeeklyStatsFileInfo, importWeeklyStatsCsv } from "../api";
import type { WeeklyStatsFileStatus, WeeklyStatsPosition } from "../types";

// Settings' Weekly Stats panel -- the 4 FantasyData exports (QB/RB/WR/TE)
// that feed DK Players' "Update Week N Points" action (see
// backend/services/dk_players/weekly_stats_loader.py for the column shape
// each one has). Not platform-scoped -- these are league-wide stats, not
// tied to a DK contest. `onUploaded` lets Settings refresh the combined
// status list below after any one of the 4 uploads succeeds.
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

  async function handleUpload(position: WeeklyStatsPosition) {
    const file = files[position];
    if (!file) return;
    setUploading(position);
    setMessages((prev) => ({ ...prev, [position]: null }));
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

  return (
    <div className="weekly-stats-upload">
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
    </div>
  );
}

interface WeeklyStatsFileStatusListProps {
  season: number;
  week: number;
  refreshToken: number;
}

// All 4 positions' current upload status -- mirrors FileUploadStatus's
// "<filename> modified <timestamp>" display, just for 4 files at once
// rather than one, since that's how the file-info endpoint reports them.
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
          {f.filename ? `${f.filename} modified ${new Date(f.uploaded_at as string).toLocaleString()}` : "not uploaded"}
        </li>
      ))}
    </ul>
  );
}
