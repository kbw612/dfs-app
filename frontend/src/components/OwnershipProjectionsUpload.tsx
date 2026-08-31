import { useState } from "react";
import { importOwnershipProjectionsCsv } from "../api";

// Settings tab's single-file ownership projections upload (offense + DST
// rows together -- see backend/api/ownership/upload_projections_csv.py).
// Separate from the Ownership tab's own "Load ownership data" flow, which
// still drives its scrape-stand-in analysis.
interface OwnershipProjectionsUploadProps {
  season: number;
  week: number;
  platform: string;
  onUploaded: () => void;
}

export function OwnershipProjectionsUpload({ season, week, platform, onUploaded }: OwnershipProjectionsUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setMessage(null);
    try {
      const result = await importOwnershipProjectionsCsv(season, week, platform, file);
      setMessage(`Loaded ${result.player_count} players`);
      setFile(null);
      onUploaded();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to upload ownership file");
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
