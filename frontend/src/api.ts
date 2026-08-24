import type {
  DiffResult,
  OwnershipImportResult,
  OwnershipLatestResult,
  ScrapeResult,
  SnapshotSummary,
  UsageBumpsResult,
} from "./types";

// Falls back to the backend's default local port -- see .env.example if
// you're running the API somewhere else.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

class ApiError extends Error {}

async function parseErrorDetail(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  if (body && typeof body === "object" && "detail" in body) {
    return String((body as { detail: unknown }).detail);
  }
  return response.statusText;
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response));
  }
  return (await response.json()) as T;
}

async function apiPost<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST" });
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response));
  }
  return (await response.json()) as T;
}

export function listSnapshots(): Promise<SnapshotSummary[]> {
  return apiGet<SnapshotSummary[]>("/api/depth-charts/snapshots");
}

export function fetchDiffLatest(): Promise<DiffResult> {
  return apiGet<DiffResult>("/api/depth-charts/diff/latest");
}

export function fetchDiffCompare(from: string, to: string): Promise<DiffResult> {
  const params = new URLSearchParams({ from, to });
  return apiGet<DiffResult>(`/api/depth-charts/diff?${params.toString()}`);
}

export function triggerScrape(): Promise<ScrapeResult> {
  return apiPost<ScrapeResult>("/api/depth-charts/scrape");
}

export function fetchUsageBumpsLatest(): Promise<UsageBumpsResult> {
  return apiGet<UsageBumpsResult>("/api/opportunities/latest");
}

// Temporary stand-in for a live ownership scrape -- reads the mock CSVs in
// data/ownership_mock/ instead (see import_csv.py's docstring). Swapping
// this for a real POST /api/ownership/scrape later is a one-line change
// here; nothing else in OwnershipView needs to know which one ran.
export function importOwnershipCsv(season: number, week: number): Promise<OwnershipImportResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiPost<OwnershipImportResult>(`/api/ownership/import-csv?${params.toString()}`);
}

export function fetchOwnershipLatest(season: number, week: number): Promise<OwnershipLatestResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiGet<OwnershipLatestResult>(`/api/ownership/latest?${params.toString()}`);
}
