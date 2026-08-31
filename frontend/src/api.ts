import type {
  CurrentWeek,
  DiffResult,
  DkSalaryImportResult,
  FileInfo,
  GameEnvironmentEntry,
  OwnershipImportResult,
  OwnershipLatestResult,
  OwnershipProjectionsImportResult,
  PlatformSettings,
  PlayerAttributeEntryInput,
  PlayerPoolEntryInput,
  PlayerPoolResult,
  PlayerSelectionEntryInput,
  PlayerSelectionResult,
  PositionBlocksResult,
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

async function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "POST", body: formData });
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response));
  }
  return (await response.json()) as T;
}

async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(await parseErrorDetail(response));
  }
  return (await response.json()) as T;
}

// The single shared (season, week) pointer -- see
// backend/api/current_week/__init__.py. Read once on app load, written
// whenever the shared header control changes.
export function fetchCurrentWeek(): Promise<CurrentWeek> {
  return apiGet<CurrentWeek>("/api/current-week");
}

export function saveCurrentWeek(entry: CurrentWeek): Promise<CurrentWeek> {
  return apiPut<CurrentWeek>("/api/current-week", entry);
}

// The single shared (platform, contest) pointer -- see
// backend/api/platform_settings/__init__.py. Read once on app load,
// written whenever Settings' Platform/Contest panel changes.
export function fetchPlatformSettings(): Promise<PlatformSettings> {
  return apiGet<PlatformSettings>("/api/platform-settings");
}

export function savePlatformSettings(entry: PlatformSettings): Promise<PlatformSettings> {
  return apiPut<PlatformSettings>("/api/platform-settings", entry);
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

export interface PositionBlocksParams {
  season: number;
  week: number;
  position: string;
  blockSize: number;
  sameGameOnly: boolean;
  teams: string[];
  games: string[];
  platform: string;
  salaryBuckets: string[];
}

export function fetchPositionBlocks(params: PositionBlocksParams): Promise<PositionBlocksResult> {
  const query = new URLSearchParams({
    season: String(params.season),
    week: String(params.week),
    position: params.position,
    block_size: String(params.blockSize),
    same_game_only: String(params.sameGameOnly),
    platform: params.platform,
  });
  for (const team of params.teams) query.append("team", team);
  for (const game of params.games) query.append("game", game);
  for (const bucket of params.salaryBuckets) query.append("salary_bucket", bucket);
  return apiGet<PositionBlocksResult>(`/api/ownership/position-blocks?${query.toString()}`);
}

export function fetchPlayerPool(season: number, week: number, platform: string): Promise<PlayerPoolResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiGet<PlayerPoolResult>(`/api/player-pool/latest?${params.toString()}`);
}

export function savePlayerPoolEntry(entry: PlayerPoolEntryInput): Promise<PlayerPoolEntryInput> {
  return apiPut<PlayerPoolEntryInput>("/api/player-pool/entry", entry);
}

// Shared across tabs (not player-pool-specific) -- see
// backend/api/player_attributes/__init__.py.
export function savePlayerAttributeEntry(entry: PlayerAttributeEntryInput): Promise<PlayerAttributeEntryInput> {
  return apiPut<PlayerAttributeEntryInput>("/api/player-attributes/entry", entry);
}

// Settings' Player Selection grid -- every QB/RB/WR/TE from this week's
// salary file plus its computed selected state (see
// backend/api/player_selection/latest.py). Deselecting a player here is
// what narrows the pool shown in Player Pool and Salary Blocks.
export function fetchPlayerSelection(season: number, week: number, platform: string): Promise<PlayerSelectionResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiGet<PlayerSelectionResult>(`/api/player-selection/latest?${params.toString()}`);
}

export function savePlayerSelectionEntry(entry: PlayerSelectionEntryInput): Promise<PlayerSelectionEntryInput> {
  return apiPut<PlayerSelectionEntryInput>("/api/player-selection/entry", entry);
}

// Shared across tabs (not player-pool-specific) -- see
// backend/api/game_environment/__init__.py.
export function saveGameEnvironment(entry: GameEnvironmentEntry): Promise<GameEnvironmentEntry> {
  return apiPut<GameEnvironmentEntry>("/api/game-environment/entry", entry);
}

// Uploads DK's own native salary export -- shared by Salary Blocks and
// Player Pool (see backend/services/dk_salary/dk_salary_loader.py),
// independent of whatever the Ownership tab has loaded. `platform` picks
// the filename prefix the file gets saved under (see
// backend/services/platform_settings/prefix.py) -- Settings sends
// whichever platform is currently selected in its top panel.
export function importDkSalaryCsv(
  season: number,
  week: number,
  platform: string,
  file: File
): Promise<DkSalaryImportResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<DkSalaryImportResult>(`/api/dk-salary/import-csv?${params.toString()}`, formData);
}

// {filename, uploaded_at} for whatever's currently saved -- Settings shows
// this as plain, non-clickable text rather than a link to the file
// itself (see FileUploadStatus.tsx). Rejects (404) if nothing's been
// uploaded yet for that (season, week, platform).
export function fetchDkSalaryFileInfo(season: number, week: number, platform: string): Promise<FileInfo> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiGet<FileInfo>(`/api/dk-salary/file-info?${params.toString()}`);
}

export function fetchOwnershipProjectionsFileInfo(
  season: number,
  week: number,
  platform: string
): Promise<FileInfo> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiGet<FileInfo>(`/api/ownership/projections-file-info?${params.toString()}`);
}

// Settings tab's single-file ownership projections upload (offense + DST
// rows together) -- separate from importOwnershipCsv above, which still
// drives the Ownership tab's own scrape-stand-in analysis. `platform`
// picks the filename prefix, same as importDkSalaryCsv above.
export function importOwnershipProjectionsCsv(
  season: number,
  week: number,
  platform: string,
  file: File
): Promise<OwnershipProjectionsImportResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<OwnershipProjectionsImportResult>(
    `/api/ownership/upload-projections-csv?${params.toString()}`,
    formData
  );
}
