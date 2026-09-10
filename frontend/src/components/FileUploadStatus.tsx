import { useEffect, useState } from "react";
import type { FileInfo } from "../types";

interface FileUploadStatusProps {
  season: number;
  week: number;
  platform: string;
  // Defaults to "Classic Main" so a future caller whose file-info fetcher
  // isn't contest-scoped doesn't have to pass anything.
  contest?: string;
  // The actual named api.ts function (fetchDkSalaryFileInfo or
  // fetchContestStandingsFileInfo) -- passed directly rather than wrapped
  // in a closure so it's referentially stable across renders and safe to
  // list in the effect's dependency array.
  fetchInfo: (season: number, week: number, platform: string, contest: string) => Promise<FileInfo>;
  refreshToken: number;
}

// Plain, non-clickable "<filename> modified <timestamp>" text -- replaces
// the old FileViewLink, which rendered a clickable link to the file
// itself. Renders nothing if no file has been uploaded yet for this
// (season, week, platform, contest).
export function FileUploadStatus({
  season,
  week,
  platform,
  contest = "Classic Main",
  fetchInfo,
  refreshToken,
}: FileUploadStatusProps) {
  const [info, setInfo] = useState<FileInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    fetchInfo(season, week, platform, contest)
      .then((result) => {
        if (!cancelled) setInfo(result);
      })
      .catch(() => {
        if (!cancelled) setInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, platform, contest, fetchInfo, refreshToken]);

  if (!info) return null;

  return (
    <p className="settings-file-status">
      {info.filename} modified {new Date(info.uploaded_at).toLocaleString()}
    </p>
  );
}
