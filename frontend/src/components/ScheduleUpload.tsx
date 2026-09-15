import { useEffect, useState } from "react";
import { fetchScheduleFileInfo, importScheduleCsv } from "../api";
import type { FileInfo } from "../types";

// Season-scoped only -- unlike every other Settings upload, the Schedule
// file has no week/platform/contest dimension (see
// backend/repositories/schedule/schedule_repo.py: one file per season).
// That's also why this doesn't reuse FileUploadStatus, whose fetchInfo
// signature requires week/platform/contest -- this rolls its own status
// display inline instead.
interface ScheduleUploadProps {
  season: number;
  refreshToken: number;
  onUploaded: () => void;
}

export function ScheduleUpload({ season, refreshToken, onUploaded }: ScheduleUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [info, setInfo] = useState<FileInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    fetchScheduleFileInfo(season)
      .then((result) => {
        if (!cancelled) setInfo(result);
      })
      .catch(() => {
        if (!cancelled) setInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [season, refreshToken]);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setMessage(null);
    try {
      const result = await importScheduleCsv(season, file);
      setMessage(`Loaded ${result.row_count} rows`);
      setFile(null);
      onUploaded();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to upload schedule file");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="player-pool-upload">
      <label className="player-pool-upload-label">
        <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <button type="button" className="player-pool-save-button" disabled={!file || uploading} onClick={handleUpload}>
        {uploading ? "Uploading…" : "Upload"}
      </button>
      {message && <span className="hint">{message}</span>}
      {info && (
        <p className="settings-file-status">
          {info.filename} modified {new Date(info.uploaded_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}
