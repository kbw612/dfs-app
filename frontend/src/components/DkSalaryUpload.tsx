import { useState } from "react";
import { importDkSalaryCsv } from "../api";

// Shared upload control -- Salary Blocks and Player Pool both need this
// week's DK salary export loaded, and both read the same snapshot (see
// backend/api/dk_salary/import_csv.py), so uploading from either tab
// feeds both. `onUploaded` lets the caller refetch its own data after a
// successful upload.
interface DkSalaryUploadProps {
  season: number;
  week: number;
  platform: string;
  onUploaded: () => void;
}

export function DkSalaryUpload({ season, week, platform, onUploaded }: DkSalaryUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setMessage(null);
    try {
      const result = await importDkSalaryCsv(season, week, platform, file);
      setMessage(`Loaded ${result.player_count} players`);
      setFile(null);
      onUploaded();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to upload salary file");
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
