import type {
  AddWeekPlayersResult,
  CalculateWeekPointsResult,
  ContestResultRowsResult,
  ContestStandingsImportResult,
  ContestTopLineupsResult,
  CurrentWeek,
  DepthChartRosterPlayer,
  DepthChartSnapshot,
  DiffResult,
  DkPlayersResult,
  DkPlayersWeekStatus,
  DkSalaryImportResult,
  DstTrendsResult,
  FileInfo,
  GameBlocksResult,
  GameEnvironmentEntry,
  GameLogsAgainstResult,
  GameLogsResult,
  GamePreviewResult,
  GameRecapScrapeResult,
  GameRecapWeekSnapshot,
  InjuryReportResult,
  LineupScenarioAnalysis,
  LineupScenarioDefinition,
  LineupScenarioUploadResult,
  MatchupResetResult,
  MultipliersResult,
  MyPlayerPoolEntryInput,
  NameAlias,
  NameAliasesResult,
  OptimalLineupsResult,
  OwnershipLatestResult,
  OwnershipProjectionsFileInfo,
  OwnershipMainSlateScrapeResult,
  OwnershipProjectionsImportResult,
  OwnershipProjectionsResult,
  OwnershipScoresApplyResult,
  OwnershipSummaryResult,
  PlatformSettings,
  PlayerDefaultEntryInput,
  PlayerPoolEntryInput,
  PlayerPoolResult,
  PlayerSelectionEntryInput,
  PlayerSelectionResult,
  PositionBlocksResult,
  SalaryMultiplierEntryInput,
  SalaryMultiplierResult,
  ScheduleGamesResult,
  ScheduleImportResult,
  ScrapeResult,
  SnapshotSummary,
  StarPlayerEntryInput,
  StarPlayersResult,
  TeamFactorEntryInput,
  UsageBumpPlayersResult,
  UsageBumpsResult,
  VegasLinesApplyResult,
  VegasLinesScrapeResult,
  VegasLinesSnapshot,
  WeatherScoresApplyResult,
  WeatherScrapeResult,
  WeatherSnapshot,
  WeeklyStatsFileInfoResult,
  WeeklyStatsScrapeResult,
} from "./types";

// Falls back to the backend's default local port -- see .env if
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

// Same JSON-body shape as apiPut above, just a POST -- for endpoints like
// Lineup Scenarios' /evaluate that create/compute something from a body
// rather than replacing a saved resource wholesale.
async function apiPostJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
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

// The single shared (platform, contest) pointer, scoped per season -- see
// backend/api/platform_settings/__init__.py. Read whenever the current
// season is known/changes, written whenever Settings' Platform/Contest
// panel changes.
export function fetchPlatformSettings(season: number): Promise<PlatformSettings> {
  const params = new URLSearchParams({ season: String(season) });
  return apiGet<PlatformSettings>(`/api/platform-settings?${params.toString()}`);
}

export function savePlatformSettings(entry: PlatformSettings): Promise<PlatformSettings> {
  return apiPut<PlatformSettings>("/api/platform-settings", entry);
}

// Settings' Salary Multiplier field -- see backend/api/salary_multiplier/
// __init__.py. Scoped to platform alone, no season/week. `multiplier` is
// always the resolved value; Player Rankings' Expected FPTS column reads
// this to label its header (e.g. "Expected FPTS (4x)"), and the same
// resolved value is applied server-side inside fetchPlayerPool/
// fetchMyPlayerPool's PlayerPoolPlayer.expected_fpts.
export function fetchSalaryMultiplier(platform: string): Promise<SalaryMultiplierResult> {
  const params = new URLSearchParams({ platform });
  return apiGet<SalaryMultiplierResult>(`/api/salary-multiplier/latest?${params.toString()}`);
}

export function saveSalaryMultiplierEntry(entry: SalaryMultiplierEntryInput): Promise<SalaryMultiplierResult> {
  return apiPut<SalaryMultiplierResult>("/api/salary-multiplier/entry", entry);
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

// The latest depth-chart snapshot, flattened for Settings' Player Default
// Factors grid -- see backend/api/depth_charts/roster.py. No season/week/
// platform params -- unlike everything else that panel used to depend on
// via fetchPlayerPool, this roster is the same regardless of which week
// or contest is selected.
export function fetchDepthChartRoster(): Promise<{ players: DepthChartRosterPlayer[] }> {
  return apiGet<{ players: DepthChartRosterPlayer[] }>("/api/depth-charts/roster");
}

// The full latest depth-chart snapshot (every team, every position, every
// player's status) -- see backend/api/depth_charts/latest.py. Backs the
// Depth Charts tab's by-team browse view (DepthChartsView.tsx), unlike
// fetchDepthChartRoster above (offense-only, no status, built for a
// different purpose). 404s until at least one scrape has been retrieved
// from the Compare Depth Charts tab.
export function fetchDepthChartLatest(): Promise<DepthChartSnapshot> {
  return apiGet<DepthChartSnapshot>("/api/depth-charts/latest");
}

export function fetchUsageBumpsLatest(): Promise<UsageBumpsResult> {
  return apiGet<UsageBumpsResult>("/api/opportunities/latest");
}

// Ownership Pivots (OwnershipView) reads whatever's currently uploaded via
// Settings' Ownership file upload -- the same *current* file GET
// /api/ownership/projections reads for Ownership Summary (see
// backend/api/ownership/latest.py's docstring) -- so there's no separate
// "load"/import step here anymore.
export function fetchOwnershipLatest(season: number, week: number, platform: string): Promise<OwnershipLatestResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
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
  contest: string;
  salaryBuckets: string[];
  // "Same team players" filter -- keeps only blocks whose largest
  // same-team grouping is exactly one of these sizes (see backend/
  // services/ownership/position_blocks.py's filter_blocks_by_same_team_size).
  sameTeamSizes: number[];
  // Independent, both-optional pool filters -- Settings' Player Selection
  // (defaults true, matching this endpoint's behavior before either became
  // optional) and My Player Pool's own saved shortlist (defaults false,
  // since it's the newer/narrower of the two). See backend/api/ownership/
  // position_blocks.py's docstring for why these aren't mutually exclusive.
  useSettingsPool?: boolean;
  useMyPlayerPool?: boolean;
}

export function fetchPositionBlocks(params: PositionBlocksParams): Promise<PositionBlocksResult> {
  const query = new URLSearchParams({
    season: String(params.season),
    week: String(params.week),
    position: params.position,
    block_size: String(params.blockSize),
    same_game_only: String(params.sameGameOnly),
    platform: params.platform,
    contest: params.contest,
    apply_selection_filter: String(params.useSettingsPool ?? true),
    apply_my_player_pool_filter: String(params.useMyPlayerPool ?? false),
  });
  for (const team of params.teams) query.append("team", team);
  for (const game of params.games) query.append("game", game);
  for (const bucket of params.salaryBuckets) query.append("salary_bucket", bucket);
  for (const size of params.sameTeamSizes) query.append("same_team_size", String(size));
  return apiGet<PositionBlocksResult>(`/api/ownership/position-blocks?${query.toString()}`);
}

// Onslaught's own params -- no position/blockSize/sameGameOnly (a game
// block is always RB/WR/TE mixed, one game -- see backend/api/ownership/
// game_blocks.py's docstring). primarySizes narrows by the majority
// ("team") side's count, bringbackSizes by the minority ("bring back
// team") side's count -- Onslaught's own two size filters. maxSize
// defaults to the backend's own default (5) when omitted -- Onslaught's UI
// requests a higher one (7) so its size filters have bigger blocks to
// match against.
export interface GameBlocksParams {
  season: number;
  week: number;
  teams: string[];
  games: string[];
  platform: string;
  contest: string;
  salaryBuckets: string[];
  primarySizes: number[];
  bringbackSizes: number[];
  maxSize?: number;
  // Skips block generation entirely server-side, returning just `games`
  // (see backend/api/ownership/game_blocks.py's docstring) -- Onslaught's
  // own "Filter by game" chips populate from this, before the person has
  // picked a game to actually retrieve blocks for. Defaults to false.
  gamesOnly?: boolean;
  // Same two independent, both-optional pool filters as
  // PositionBlocksParams above -- see that interface's own comment.
  useSettingsPool?: boolean;
  useMyPlayerPool?: boolean;
  // Adds one QB from either team in the game as an extra slot on top of
  // each RB/WR/TE combination -- see backend/services/ownership/
  // game_blocks.py's compute_game_blocks docstring. Defaults to true
  // (Onslaught's own toggle starts checked).
  includeQb?: boolean;
}

export function fetchGameBlocks(params: GameBlocksParams): Promise<GameBlocksResult> {
  const query = new URLSearchParams({
    season: String(params.season),
    week: String(params.week),
    platform: params.platform,
    contest: params.contest,
    apply_selection_filter: String(params.useSettingsPool ?? true),
    apply_my_player_pool_filter: String(params.useMyPlayerPool ?? false),
    include_qb: String(params.includeQb ?? true),
  });
  if (params.gamesOnly) query.set("games_only", "true");
  if (params.maxSize !== undefined) query.set("max_size", String(params.maxSize));
  for (const team of params.teams) query.append("team", team);
  for (const game of params.games) query.append("game", game);
  for (const bucket of params.salaryBuckets) query.append("salary_bucket", bucket);
  for (const size of params.primarySizes) query.append("primary_size", String(size));
  for (const size of params.bringbackSizes) query.append("bringback_size", String(size));
  return apiGet<GameBlocksResult>(`/api/ownership/game-blocks?${query.toString()}`);
}

// Contest Results tab -- uploads a person's own downloaded DraftKings
// contest standings export (see backend/services/contest_results/
// contest_standings_parser.py for the raw file's column shape). Same
// "always overwritten, re-parsed fresh on every read" convention as
// importDkSalaryCsv above, just its own separate file/endpoint.
export function importContestStandingsCsv(
  season: number,
  week: number,
  platform: string,
  contest: string,
  file: File
): Promise<ContestStandingsImportResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<ContestStandingsImportResult>(`/api/contest-results/import-csv?${params.toString()}`, formData);
}

// The first `topN` entries from this week's uploaded contest standings,
// each already joined against the week's DK salary file -- see backend/
// api/contest_results/top_lineups.py.
export function fetchContestTopLineups(
  season: number,
  week: number,
  platform: string,
  contest: string,
  topN: number
): Promise<ContestTopLineupsResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    platform,
    contest,
    top_n: String(topN),
  });
  return apiGet<ContestTopLineupsResult>(`/api/contest-results/top-lineups?${params.toString()}`);
}

// This week's full contest player-reference table, Salary joined in --
// see backend/api/contest_results/player_results.py.
export function fetchContestResultRows(
  season: number,
  week: number,
  platform: string,
  contest: string
): Promise<ContestResultRowsResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  return apiGet<ContestResultRowsResult>(`/api/contest-results/player-results?${params.toString()}`);
}

// The 10 exact-highest-scoring distinct lineups under `salaryCap` --
// cached server-side to a JSON file after the first generation for a
// given week; pass regenerate=true to force a fresh generation. See
// backend/api/contest_results/optimal_lineup_pools.py.
export function fetchOptimalLineupsTop10(
  season: number,
  week: number,
  platform: string,
  contest: string,
  salaryCap: number,
  regenerate = false
): Promise<OptimalLineupsResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    platform,
    contest,
    salary_cap: String(salaryCap),
    regenerate: String(regenerate),
  });
  return apiGet<OptimalLineupsResult>(`/api/contest-results/optimal-lineups-top10?${params.toString()}`);
}

// {filename, uploaded_at} for whatever contest standings file is
// currently saved -- see backend/api/contest_results/file_info.py. Same
// shape/purpose as fetchDkSalaryFileInfo below, for FileUploadStatus's
// shared "<filename> modified <timestamp>" display in Settings.
export function fetchContestStandingsFileInfo(
  season: number,
  week: number,
  platform: string,
  contest: string
): Promise<FileInfo> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  return apiGet<FileInfo>(`/api/contest-results/file-info?${params.toString()}`);
}

// DK Players tab -- the season-long tracker (see backend/schemas/
// dk_players/dk_players.py). Omit `week` to get every week loaded so far
// (the "All" chip).
export function fetchDkPlayers(season: number, platform: string, week?: number): Promise<DkPlayersResult> {
  const params = new URLSearchParams({ season: String(season), platform });
  if (week !== undefined) params.set("week", String(week));
  return apiGet<DkPlayersResult>(`/api/dk-players/list?${params.toString()}`);
}

// Checked before calling addDkPlayersWeek so the "replace week N?" confirm
// dialog can be worded accurately -- see backend/api/dk_players/
// week_status.py.
export function fetchDkPlayersWeekStatus(season: number, week: number, platform: string): Promise<DkPlayersWeekStatus> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiGet<DkPlayersWeekStatus>(`/api/dk-players/week-status?${params.toString()}`);
}

// "Add Week N Players" -- reads the *All Games* Salary File for this
// (season, week, platform), regardless of whatever contest is currently
// selected in Settings (see backend/api/dk_players/add_week.py's
// docstring for why), and appends those players to the tracker. 409s if
// the week already has rows unless confirmReplace is true.
export function addDkPlayersWeek(
  season: number,
  week: number,
  platform: string,
  confirmReplace = false
): Promise<AddWeekPlayersResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    platform,
    confirm_replace: String(confirmReplace),
  });
  return apiPost<AddWeekPlayersResult>(`/api/dk-players/add-week?${params.toString()}`);
}

// "Update Week N Points" -- combines the 4 FantasyData stat files'
// touchdown counts with the *All Games* Contest Standings' own FPTS/
// %Drafted (same "always All Games, not whatever's selected in Settings"
// reasoning as addDkPlayersWeek above) -- see backend/services/
// dk_players/dk_players_engine.py's calculate_week_points.
export function calculateDkPlayersWeekPoints(
  season: number,
  week: number,
  platform: string
): Promise<CalculateWeekPointsResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiPost<CalculateWeekPointsResult>(`/api/dk-players/calculate-week-points?${params.toString()}`);
}

// All 4 positions' upload status at once, for Settings' single combined
// Weekly Stats panel -- see backend/api/dk_players/weekly_stats.py.
export function fetchWeeklyStatsFileInfo(season: number, week: number): Promise<WeeklyStatsFileInfoResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiGet<WeeklyStatsFileInfoResult>(`/api/dk-players/weekly-stats/file-info?${params.toString()}`);
}

// Scrapes all 4 positions from FantasyData in one call and saves whichever
// ones succeed -- see backend/api/dk_players/weekly_stats.py. Callers
// should check fetchWeeklyStatsFileInfo first and confirm with the user
// before calling this if any position already has saved data for the
// target week, since this always overwrites.
export function scrapeWeeklyStats(season: number, week: number): Promise<WeeklyStatsScrapeResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiPost<WeeklyStatsScrapeResult>(`/api/dk-players/weekly-stats/scrape?${params.toString()}`);
}

// Name Aliases -- global list (not season/week/platform-scoped), see
// backend/api/name_aliases/__init__.py. saveNameAliases always replaces
// the whole list.
export function fetchNameAliases(): Promise<NameAliasesResult> {
  return apiGet<NameAliasesResult>("/api/name-aliases");
}

export function saveNameAliases(aliases: NameAlias[]): Promise<NameAliasesResult> {
  return apiPut<NameAliasesResult>("/api/name-aliases", { aliases });
}

// Usage Bump Players -- global list (not season/week/platform-scoped),
// see backend/api/usage_bump/players.py. saveUsageBumpPlayers always
// replaces the whole list, same convention as Name Aliases' own save.
export function fetchUsageBumpPlayers(): Promise<UsageBumpPlayersResult> {
  return apiGet<UsageBumpPlayersResult>("/api/usage-bump-players");
}

export function saveUsageBumpPlayers(result: UsageBumpPlayersResult): Promise<UsageBumpPlayersResult> {
  return apiPut<UsageBumpPlayersResult>("/api/usage-bump-players", result);
}

// Schedule -- one full-season Team/Week/Opponent/GameLocation file per
// season (see backend/api/schedule/__init__.py), not week/platform/
// contest-scoped like most uploads here. Feeds the Game Logs tab's
// Opponent/GameLoc columns and Game filter.
export function importScheduleCsv(season: number, file: File): Promise<ScheduleImportResult> {
  const params = new URLSearchParams({ season: String(season) });
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<ScheduleImportResult>(`/api/schedule/import-csv?${params.toString()}`, formData);
}

export function fetchScheduleFileInfo(season: number): Promise<FileInfo> {
  const params = new URLSearchParams({ season: String(season) });
  return apiGet<FileInfo>(`/api/schedule/file-info?${params.toString()}`);
}

// Game Logs -- see backend/api/game_logs/game_logs.py. Returns every
// currently-rostered QB/RB/WR/TE league-wide with their own recent-weeks
// history; the Game Logs tab's Team/Game chip filters narrow this
// client-side, same convention as every other tab's Position filter.
export function fetchGameLogs(
  season: number,
  week: number,
  platform: string,
  lookbackWeeks: number,
  contest: string
): Promise<GameLogsResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    platform,
    lookback_weeks: String(lookbackWeeks),
    contest,
  });
  return apiGet<GameLogsResult>(`/api/game-logs?${params.toString()}`);
}

// Game Logs Against -- see backend/api/game_logs_against/game_logs_against.py.
// Unlike fetchGameLogs, this is already scoped to this week's slate
// (one "Against {team}" panel per team appearing in `games`) -- the Game
// filter narrows to one game's two panels client-side, same shared-Game-
// filter shape as Game Logs itself.
export function fetchGameLogsAgainst(
  season: number,
  week: number,
  platform: string,
  lookbackWeeks: number,
  contest: string
): Promise<GameLogsAgainstResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    platform,
    lookback_weeks: String(lookbackWeeks),
    contest,
  });
  return apiGet<GameLogsAgainstResult>(`/api/game-logs-against?${params.toString()}`);
}

// Multipliers -- see backend/api/multipliers/multipliers.py. Always reviews
// `week - 1` (the base week) regardless of the currently-selected week's own
// tracker/lookback state -- same "last week's own box score plus trailing
// Multiplier history" shape as the backend engine returns, just passed
// through untouched; the tab does its own filtering/sorting client-side.
export function fetchDstTrends(season: number, week: number, windowWeeks: number): Promise<DstTrendsResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    window_weeks: String(windowWeeks),
  });
  return apiGet<DstTrendsResult>(`/api/dst-trends?${params.toString()}`);
}

// Game Preview -- see backend/api/game_preview/game_preview.py. Unlike
// Multipliers/DST Trends, this reviews `week` itself (the upcoming game),
// not `week - 1` -- see that endpoint's own docstring. `windowWeeks`
// scopes the DST/Off Trends matchup piece only (the one part of this tab
// that does look backward); `platform` scopes the DK Players tracker and
// Ownership projections files Phase B's own player tags read from, same
// "DraftKings" default as every other platform-scoped endpoint;
// `contest` narrows the game list to that contest's own DK salary slate,
// same convention as Game Logs/Game Logs Against.
export function fetchGamePreview(
  season: number,
  week: number,
  windowWeeks: number,
  platform: string,
  contest: string
): Promise<GamePreviewResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    window_weeks: String(windowWeeks),
    platform,
    contest,
  });
  return apiGet<GamePreviewResult>(`/api/game-preview?${params.toString()}`);
}

export function fetchMultipliers(
  season: number,
  week: number,
  platform: string,
  contest: string,
  trailingWeeks: number
): Promise<MultipliersResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    platform,
    contest,
    trailing_weeks: String(trailingWeeks),
  });
  return apiGet<MultipliersResult>(`/api/multipliers?${params.toString()}`);
}

// applySelectionFilter defaults true (the Player Rankings tab's normal
// behavior -- only players Settings' Player Selection grid has kept
// checked). SettingsView's own Player Default Factors grid passes false,
// since that panel is deliberately independent of Player Selection (see
// backend/api/player_pool/latest.py's docstring).
export function fetchPlayerPool(
  season: number,
  week: number,
  platform: string,
  contest: string,
  applySelectionFilter = true,
): Promise<PlayerPoolResult> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    platform,
    contest,
    apply_selection_filter: String(applySelectionFilter),
  });
  return apiGet<PlayerPoolResult>(`/api/player-pool/latest?${params.toString()}`);
}

export function savePlayerPoolEntry(entry: PlayerPoolEntryInput): Promise<PlayerPoolEntryInput> {
  return apiPut<PlayerPoolEntryInput>("/api/player-pool/entry", entry);
}

// Bulk-computes and saves each player's Ownership score from their
// current ownership_pct -- see backend/api/player_pool/
// calculate_ownership_scores.py. Mirrors applyVegasLines' role for Game
// Environment; 404s if no Ownership projections have been uploaded yet
// for this (season, week, platform), same as fetchPlayerPool's own "no DK
// salary uploaded yet" case for the salary file.
export function calculateOwnershipScores(
  season: number,
  week: number,
  platform: string,
  contest: string,
): Promise<OwnershipScoresApplyResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  return apiPost<OwnershipScoresApplyResult>(`/api/player-pool/calculate-ownership-scores?${params.toString()}`);
}

// Player Rankings' DST-only Weather refresh icon -- see backend/api/
// player_pool/calculate_weather_scores.py. Same "latest applied wins" bulk
// overwrite as calculateOwnershipScores above.
export function calculateWeatherScores(
  season: number,
  week: number,
  platform: string,
  contest: string,
): Promise<WeatherScoresApplyResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  return apiPost<WeatherScoresApplyResult>(`/api/player-pool/calculate-weather-scores?${params.toString()}`);
}

// Player Rankings' DST-only Matchup refresh icon -- see backend/api/
// player_pool/reset_matchup.py. Clears this week's explicit Matchup
// override for every player at `position` so it falls back to the
// opponent's own Team Default Factor (or the flat 2.0 neutral).
export function resetMatchupToTeamFactor(
  season: number,
  week: number,
  platform: string,
  contest: string,
  position: string,
): Promise<MatchupResetResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest, position });
  return apiPost<MatchupResetResult>(`/api/player-pool/reset-matchup-to-team-factor?${params.toString()}`);
}

// My Player Pool tab -- see backend/api/my_player_pool/latest.py. Returns
// only the players explicitly added to this personal shortlist, each
// with the same computed row shape fetchPlayerPool returns (reused
// directly server-side -- see PlayerPoolResult). Independent of Player
// Selection, so there's no applySelectionFilter param here.
export function fetchMyPlayerPool(
  season: number,
  week: number,
  platform: string,
  contest: string
): Promise<PlayerPoolResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  return apiGet<PlayerPoolResult>(`/api/my-player-pool/latest?${params.toString()}`);
}

export function saveMyPlayerPoolEntry(entry: MyPlayerPoolEntryInput): Promise<MyPlayerPoolEntryInput> {
  return apiPut<MyPlayerPoolEntryInput>("/api/my-player-pool/entry", entry);
}

// Settings' Player Default Factors grid -- every player's saved Default
// for a season, no week (see backend/api/player_defaults/__init__.py).
export function fetchPlayerDefaults(season: number): Promise<{ defaults: PlayerDefaultEntryInput[] }> {
  const params = new URLSearchParams({ season: String(season) });
  return apiGet<{ defaults: PlayerDefaultEntryInput[] }>(`/api/player-defaults/latest?${params.toString()}`);
}

export function savePlayerDefaultEntry(entry: PlayerDefaultEntryInput): Promise<PlayerDefaultEntryInput> {
  return apiPut<PlayerDefaultEntryInput>("/api/player-defaults/entry", entry);
}

// Settings' Team Default Factors grid -- every (team, position)'s saved
// factor for a season, no week (see backend/api/team_factors/latest.py).
export function fetchTeamFactors(season: number): Promise<{ factors: TeamFactorEntryInput[] }> {
  const params = new URLSearchParams({ season: String(season) });
  return apiGet<{ factors: TeamFactorEntryInput[] }>(`/api/team-factors/latest?${params.toString()}`);
}

export function saveTeamFactorEntry(entry: TeamFactorEntryInput): Promise<TeamFactorEntryInput> {
  return apiPut<TeamFactorEntryInput>("/api/team-factors/entry", entry);
}

// Depth Charts tab's star icon -- see backend/api/star_players/. Never
// 404s (an empty list is a normal starting state, not a "retrieve first"
// precondition). setStarPlayer echoes the full updated list so the
// frontend can sync local state from the server rather than trusting its
// own optimistic update matched.
export function fetchStarPlayers(): Promise<StarPlayersResult> {
  return apiGet<StarPlayersResult>("/api/star-players/latest");
}

export function setStarPlayer(entry: StarPlayerEntryInput): Promise<StarPlayersResult> {
  return apiPut<StarPlayersResult>("/api/star-players/entry", entry);
}

// Injury Report -- see backend/api/injury_report/latest.py. `platform`
// isn't threaded through here (the endpoint defaults it to "DraftKings" --
// this app is DK-only in practice, same simplification DK Players already
// made); season/week/contest mirror Game Logs' own fetchGameLogs.
export function fetchInjuryReport(season: number, week: number, contest: string): Promise<InjuryReportResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), contest });
  return apiGet<InjuryReportResult>(`/api/injury-report/latest?${params.toString()}`);
}

// Settings' Player Selection grid -- every QB/RB/WR/TE from this week's
// salary file plus its computed selected state (see
// backend/api/player_selection/latest.py). Deselecting a player here is
// what narrows the pool shown in Player Pool and Salary Blocks.
export function fetchPlayerSelection(
  season: number,
  week: number,
  platform: string,
  contest: string
): Promise<PlayerSelectionResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
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

// Vegas Lines tab -- see backend/api/vegas_lines/__init__.py. Fetching
// "latest" 404s until you've retrieved at least once for this
// (season, week); the caller checks for that via isNotFound, same pattern
// as fetchPlayerPool's "no DK salary uploaded yet" case.
export function fetchVegasLines(season: number, week: number): Promise<VegasLinesSnapshot> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiGet<VegasLinesSnapshot>(`/api/vegas-lines/latest?${params.toString()}`);
}

// Scrapes oneweekseason.com's public week page and merges it into
// whatever Vegas Lines already has saved for this (season, week) -- see
// backend/services/vegas_lines/merge.py's docstring for the
// initial-vs-current rule. Does not touch Game Environment/scoring by
// itself -- see applyVegasLines for that separate, explicit step.
export function scrapeVegasLines(season: number, week: number): Promise<VegasLinesScrapeResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiPost<VegasLinesScrapeResult>(`/api/vegas-lines/scrape?${params.toString()}`);
}

// Writes this week's cached Vegas Lines `current` values into Game
// Environment -- see backend/api/vegas_lines/apply.py. Does not scrape
// live itself; 404s if nothing's been retrieved yet for this week.
export function applyVegasLines(season: number, week: number): Promise<VegasLinesApplyResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiPost<VegasLinesApplyResult>(`/api/vegas-lines/apply?${params.toString()}`);
}

// Game Recaps -- see backend/api/game_recap/__init__.py. Fetching "latest"
// 404s until you've scraped at least once for this (season, week); callers
// treat that as "nothing scraped yet" rather than a real error, same
// pattern as fetchVegasLines/fetchWeather.
export function fetchGameRecaps(season: number, week: number): Promise<GameRecapWeekSnapshot> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiGet<GameRecapWeekSnapshot>(`/api/game-recap/latest?${params.toString()}`);
}

// Scrapes walterfootball.com's public recap page and fully replaces
// whatever Game Recaps already has saved for this (season, week) -- no
// merge step, same as scrapeWeather (see GameRecapWeekSnapshot's own
// docstring for why there's no initial/current split the way Vegas Lines
// has).
//
// `urlMode` mirrors the backend's UrlMode literal ("auto" | "week_page" |
// "current_page") -- see game_recap_scraper.py's scrape() docstring. Left
// undefined/"auto" preserves the original numbered-then-bare fallback;
// GameRecapUpload's radio buttons pass "week_page"/"current_page" to
// override it explicitly.
export function scrapeGameRecaps(
  season: number,
  week: number,
  urlMode?: "auto" | "week_page" | "current_page",
): Promise<GameRecapScrapeResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  if (urlMode) {
    params.set("url_mode", urlMode);
  }
  return apiPost<GameRecapScrapeResult>(`/api/game-recap/scrape?${params.toString()}`);
}

// Weather tab -- see backend/api/weather/__init__.py. Fetching "latest"
// 404s until you've retrieved at least once for this (season, week); the
// caller checks for that via isNotFound, same pattern as fetchVegasLines.
export function fetchWeather(season: number, week: number): Promise<WeatherSnapshot> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiGet<WeatherSnapshot>(`/api/weather/latest?${params.toString()}`);
}

// Scrapes mysportsweather.com/nfl's current "Kevin's note" cards and
// fully replaces whatever Weather already has saved for this
// (season, week) -- no merge step, unlike Vegas Lines (see
// backend/repositories/weather/weather_repo.py's docstring).
export function scrapeWeather(season: number, week: number): Promise<WeatherScrapeResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week) });
  return apiPost<WeatherScrapeResult>(`/api/weather/scrape?${params.toString()}`);
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
  contest: string,
  file: File
): Promise<DkSalaryImportResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<DkSalaryImportResult>(`/api/dk-salary/import-csv?${params.toString()}`, formData);
}

// {filename, uploaded_at} for whatever's currently saved -- Settings shows
// this as plain, non-clickable text rather than a link to the file
// itself (see FileUploadStatus.tsx). Rejects (404) if nothing's been
// uploaded yet for that (season, week, platform, contest).
export function fetchDkSalaryFileInfo(
  season: number,
  week: number,
  platform: string,
  contest: string
): Promise<FileInfo> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  return apiGet<FileInfo>(`/api/dk-salary/file-info?${params.toString()}`);
}

// Parsed player list from whatever's currently uploaded via Settings'
// Ownership file -- see backend/api/ownership/projections.py. Used by the
// Ownership Summary tab; distinct from fetchOwnershipLatest, which reads
// the older mock-scrape/live-scrape snapshot instead (Ownership Pivots,
// and the ownership_pct merged into Player Pool/Salary Blocks).
export function fetchOwnershipProjections(season: number, week: number, platform: string): Promise<OwnershipProjectionsResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiGet<OwnershipProjectionsResult>(`/api/ownership/projections?${params.toString()}`);
}

// Backend-computed Team/Game ownership rollups for the Ownership Summary
// tab -- see backend/api/ownership/summary.py's own docstring. `contest`
// (unlike fetchOwnershipProjections above) narrows which Contest
// Standings/DK salary file back the Actual/home-away figures.
export function fetchOwnershipSummary(
  season: number,
  week: number,
  platform: string,
  contest: string
): Promise<OwnershipSummaryResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  return apiGet<OwnershipSummaryResult>(`/api/ownership/summary?${params.toString()}`);
}

// Filename plus both the initial and current upload timestamps -- see
// backend/api/ownership/projections_file_info.py. Not reused by
// FileUploadStatus (DK Salary's own file info has no "initial" concept),
// since Settings shows both timestamps for the Ownership file explicitly.
export function fetchOwnershipProjectionsFileInfo(
  season: number,
  week: number,
  platform: string
): Promise<OwnershipProjectionsFileInfo> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiGet<OwnershipProjectionsFileInfo>(`/api/ownership/projections-file-info?${params.toString()}`);
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

// Scrapes OneWeekSeason's public DraftKings Main Slate page and saves the
// result through the same file the manual upload above writes to -- see
// backend/api/ownership/scrape_main_slate.py. No file to attach; this is a
// second way to produce that same CSV, offered as an alternative to the
// upload, not a replacement for it.
export function scrapeMainSlateOwnership(
  season: number,
  week: number,
  platform: string
): Promise<OwnershipMainSlateScrapeResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform });
  return apiPost<OwnershipMainSlateScrapeResult>(`/api/ownership/scrape-main-slate?${params.toString()}`);
}

// Lineup Scenarios tab -- see backend/api/schedule/games.py,
// backend/api/lineup_scenarios/upload_csv.py and .../evaluate.py.

// This week's games (from the Schedule file, narrowed to the current
// contest's own slate) -- backs the scenario builder's away/home
// checkboxes.
export function fetchScheduleGames(
  season: number,
  week: number,
  platform: string,
  contest: string
): Promise<ScheduleGamesResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  return apiGet<ScheduleGamesResult>(`/api/schedule/games?${params.toString()}`);
}

// Uploads a person's own already-built lineups export (from an external
// optimizer) -- see lineup_upload_parser.py for the expected column
// shape (a roster-position header row, then one row per lineup).
export function uploadLineupScenarioCsv(
  season: number,
  week: number,
  platform: string,
  contest: string,
  file: File
): Promise<LineupScenarioUploadResult> {
  const params = new URLSearchParams({ season: String(season), week: String(week), platform, contest });
  const formData = new FormData();
  formData.append("file", file);
  return apiPostForm<LineupScenarioUploadResult>(`/api/lineup-scenarios/upload?${params.toString()}`, formData);
}

// Scores every caller-built scenario against every uploaded lineup --
// see lineup_scenario_engine.py's evaluate_scenarios for the exact
// satisfaction rule (every one of a scenario's flagged teams has to
// clear minStackSize).
export function evaluateLineupScenarios(
  season: number,
  week: number,
  platform: string,
  contest: string,
  scenarios: LineupScenarioDefinition[],
  minStackSize: number
): Promise<LineupScenarioAnalysis> {
  const params = new URLSearchParams({
    season: String(season),
    week: String(week),
    platform,
    contest,
    min_stack_size: String(minStackSize),
  });
  return apiPostJson<LineupScenarioAnalysis>(`/api/lineup-scenarios/evaluate?${params.toString()}`, { scenarios });
}
