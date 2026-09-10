import { useState } from "react";
import { importContestStandingsCsv } from "../api";

// Settings' own upload for the Contest Results tab -- modeled directly on
// DkSalaryUpload.tsx (same shape, same "always overwritten, re-parsed
// fresh on every read" backing endpoint), just its own separate file/
// season/week/platform-scoped snapshot (see backend/api/contest_results/
// import_csv.py). `onUploaded` lets Settings refresh its own file-status
// display after a successful upload.
interface ContestStandingsUploadProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
  onUploaded: () => void;
}

export function ContestStandingsUpload({ season, week, platform, contest, onUploaded }: ContestStandingsUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setMessage(null);
    try {
      const result = await importContestStandingsCsv(season, week, platform, contest, file);
      setMessage(`Loaded ${result.entry_count} entries, ${result.reference_row_count} player rows`);
      setFile(null);
      onUploaded();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to upload contest standings");
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
    </div>
  );
}
