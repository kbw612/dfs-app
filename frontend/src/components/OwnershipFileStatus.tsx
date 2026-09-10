import { useEffect, useState } from "react";
import { fetchOwnershipProjectionsFileInfo } from "../api";
import type { OwnershipProjectionsFileInfo } from "../types";

interface OwnershipFileStatusProps {
  season: number;
  week: number;
  platform: string;
  refreshToken: number;
}

// Ownership file's own status display -- unlike FileUploadStatus (the
// generic "<filename> modified <timestamp>" line shared with DK Salary),
// this shows two timestamps: when this (season, week, platform) was first
// ever uploaded (never changes after that upload) and when it was most
// recently re-uploaded (e.g. Saturday's refreshed ownership numbers) --
// see backend/api/ownership/projections_file_info.py. Renders nothing if
// no file has been uploaded yet.
export function OwnershipFileStatus({ season, week, platform, refreshToken }: OwnershipFileStatusProps) {
  const [info, setInfo] = useState<OwnershipProjectionsFileInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    fetchOwnershipProjectionsFileInfo(season, week, platform)
      .then((result) => {
        if (!cancelled) setInfo(result);
      })
      .catch(() => {
        if (!cancelled) setInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, platform, refreshToken]);

  if (!info) return null;

  // Same timestamp for both lines when this file's only ever been
  // uploaded once -- shown as-is rather than collapsed into one line, so
  // it's obvious at a glance that no Saturday refresh has happened yet.
  return (
    <p className="settings-file-status">
      {info.filename}
      <br />
      Initial upload {new Date(info.initial_uploaded_at).toLocaleString()}
      <br />
      Last upload {new Date(info.uploaded_at).toLocaleString()}
    </p>
  );
}
