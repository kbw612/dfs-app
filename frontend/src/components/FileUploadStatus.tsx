import { useEffect, useState } from "react";
import type { FileInfo } from "../types";

interface FileUploadStatusProps {
  season: number;
  week: number;
  platform: string;
  // The actual named api.ts function (fetchDkSalaryFileInfo or
  // fetchOwnershipProjectionsFileInfo) -- passed directly rather than
  // wrapped in a closure so it's referentially stable across renders and
  // safe to list in the effect's dependency array.
  fetchInfo: (season: number, week: number, platform: string) => Promise<FileInfo>;
  refreshToken: number;
}

// Plain, non-clickable "<filename> modified <timestamp>" text -- replaces
// the old FileViewLink, which rendered a clickable link to the file
// itself. Renders nothing if no file has been uploaded yet for this
// (season, week, platform).
export function FileUploadStatus({ season, week, platform, fetchInfo, refreshToken }: FileUploadStatusProps) {
  const [info, setInfo] = useState<FileInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    fetchInfo(season, week, platform)
      .then((result) => {
        if (!cancelled) setInfo(result);
      })
      .catch(() => {
        if (!cancelled) setInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, platform, fetchInfo, refreshToken]);

  if (!info) return null;

  return (
    <p className="settings-file-status">
      {info.filename} modified {new Date(info.uploaded_at).toLocaleString()}
    </p>
  );
}
