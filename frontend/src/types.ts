// Mirrors the backend's Pydantic schemas exactly (see
// app/schemas/depth_charts/change.py and the response models in
// app/api/depth_charts/*.py) -- keep these two in sync by hand for now,
// there's no shared schema generation yet.

export type ChangeType = "status" | "rank" | "other";

// Player-level changes carry {status, rank} in previous/current.
// Team-level changes (field === "defensive_formation") carry a plain
// string instead. Never both at once -- see diff.py's design doc notes.
export interface PlayerChangeValue {
  status: string | null;
  rank: number;
}

export type ChangeValue = PlayerChangeValue | string | null;

export interface Change {
  team_abbrev: string | null;
  position: string | null;
  player: string | null;
  field: string | null;
  change_types: ChangeType[];
  previous: ChangeValue;
  current: ChangeValue;
}

export interface DiffResult {
  from_snapshot: string;
  to_snapshot: string;
  change_count: number;
  changes: Change[];
}

export interface SnapshotSummary {
  id: string;
  scraped_at: string;
  team_count: number;
}

export interface Message {
  level: "error" | "warning" | "info";
  step: string;
  message: string;
}

export interface ScrapeResult {
  snapshot_path: string;
  scraped_at: string;
  team_count: number;
  message_counts: Record<string, number>;
  messages: Message[];
}

// Mirrors app/schemas/usage_bump/usage_bump.py. Derived from a single
// snapshot (the latest one) -- not a diff between two, unlike Change.

// One (real) member of a trigger's resolved usage-bump list. `depth` is
// the 1-indexed position within *that list* (not the player's real
// depth-chart rank) -- matches the keys used in
// config/player-out-settings.json's bump_depth_values. `weight` is that
// matched row's value for this depth, regardless of whether this player
// happens to also be out (see UsageBumpCause.weight for what actually
// got credited). `position`/`rank` are this player's own real position
// group and depth-chart rank (lists can span positions) -- same shape as
// UsageBump.position/rank, so a role label like "WR1" renders the same
// way here as it does for the top-level UsageBump. `status` is their
// current status, or null if they're healthy.
export interface UsageBumpListEntry {
  depth: number;
  player: string;
  position: string;
  rank: number;
  status: string | null;
  weight: number;
}

export interface UsageBumpCause {
  player: string;
  status: string;
  // This trigger's own real position and depth-chart rank -- same shape
  // as UsageBump.position/rank, so a role label like "WR2" renders the
  // same way for the trigger as it does for a beneficiary.
  position: string;
  rank: number;
  weight: number;
  // The exact combination of list-positions (1-indexed) that were also
  // out -- matches config/player-out-settings.json's `player_out_depths`
  // field, both in name and shape. [0] is the sentinel for "nobody else
  // in the list is out."
  player_out_depths: number[];
  // This trigger's full resolved usage-bump list (capped at 5) -- every
  // player in it, not just the one this cause is attached to.
  usage_bump_list: UsageBumpListEntry[];
  // How this trigger's usage-bump list was resolved.
  source: "curated" | "position-settings";
  // Only set when source === "position-settings": the role label that
  // was looked up (e.g. "WR2") and its configured usageBumpPositions
  // list, verbatim -- role labels, not resolved player names.
  source_role_label: string | null;
  source_role_positions: string[] | null;
}

export interface UsageBump {
  team_abbrev: string | null;
  position: string;
  player: string;
  rank: number;
  bump_score: number;
  causes: UsageBumpCause[];
}

export interface UsageBumpsResult {
  snapshot_id: string;
  scraped_at: string;
  usage_bumps: UsageBump[];
}

export function isPlayerChangeValue(value: ChangeValue): value is PlayerChangeValue {
  return value !== null && typeof value === "object";
}

// Mirrors backend/schemas/ownership/ownership.py and the response models in
// backend/api/ownership/*.py. Unlike depth charts (nested team -> position
// -> players) this is a flat player list -- position/team/opponent are just
// columns on each row, same shape whether it came from a live scrape or the
// CSV mock loader (see csv_loader.py's docstring).
export interface OwnershipPlayer {
  player: string;
  position: string;
  team: string;
  opponent: string;
  // True if playing at the opponent's stadium; null only if the source row
  // couldn't be parsed as home/away.
  is_home: boolean | null;
  salary: number;
  // null means ownership isn't known yet -- ownership projections are
  // only available later in the week, while salary/position/team can be
  // loaded as soon as DK publishes the slate (see backend/schemas/
  // ownership/ownership.py's OwnershipPlayer.ownership_pct docstring).
  ownership_pct: number | null;
  // Depth-chart rank (e.g. RB1's "1"), cross-referenced server-side from
  // the latest depth-chart snapshot by player name -- null if there's no
  // depth-chart snapshot yet or this name didn't match one.
  rank: number | null;
}

// One NFL game with at least one chalk player on either side. chalk_players
// is every high-owned player from both teams; pivot_candidates is every
// player from both teams under the slate's leverage point.
export interface GameLeverageGroup {
  team: string;
  opponent: string;
  chalk_players: OwnershipPlayer[];
  pivot_candidates: OwnershipPlayer[];
}

// One higher-owned trigger player and every same-position, similar-salary
// player who's owned meaningfully less -- see engine.py's compute_pivots().
export interface PivotGroup {
  trigger: OwnershipPlayer;
  pivots: OwnershipPlayer[];
}

// One concrete reason a player counts toward MultiLeveragePlayer -- either
// they're the pivot for a specific higher-owned `against` ("pivot", from a
// PivotGroup), or they're a contrarian pick against one specific chalk
// player `against` in their game ("game", from a GameLeverageGroup --
// `team`/`opponent` identify which game). team/opponent are only set for
// kind "game".
export interface LeverageReason {
  kind: "pivot" | "game";
  against: OwnershipPlayer;
  team: string | null;
  opponent: string | null;
}

// A player who's worth fading/pivoting off of 2+ other players at once --
// see engine.py's compute_multi_leverage() for how `reasons` is built and
// counted (backend-computed; the frontend only buckets this list by
// reason count for display, see OwnershipView.tsx's
// groupMultiLeveragePlayers).
export interface MultiLeveragePlayer {
  player: OwnershipPlayer;
  reasons: LeverageReason[];
}

export interface OwnershipLatestResult {
  snapshot_id: string;
  scraped_at: string;
  season: number;
  week: number;
  leverage_point: number;
  players: OwnershipPlayer[];
  high_owned: OwnershipPlayer[];
  game_leverage: GameLeverageGroup[];
  pivots: PivotGroup[];
  multi_leverage: MultiLeveragePlayer[];
}

// Mirrors backend/services/ownership/position_blocks.py -- every
// fixed-size, same-position combination of players plus their combined
// salary. `players` is sorted by salary descending within the block.
export interface PositionBlock {
  players: OwnershipPlayer[];
  total_salary: number;
}

// One distinct matchup among a position's players -- `key` is the
// "TEAM1-TEAM2" form the API expects back for the `game` filter param,
// `label` is the "TEAM1 vs TEAM2" display form.
export interface GameOption {
  key: string;
  label: string;
}

export interface PositionBlocksResult {
  blocks: PositionBlock[];
  games: GameOption[];
}

// Result of POST /api/ownership/import-csv -- the temporary stand-in for a
// live scrape (see import_csv.py's docstring). Same message shape as
// ScrapeResult above.
export interface OwnershipImportResult {
  snapshot_path: string;
  scraped_at: string;
  season: number;
  week: number;
  player_count: number;
  message_counts: Record<string, number>;
  messages: Message[];
}

// Mirrors backend/schemas/player_pool/player_pool.py. Every score field is
// null until scored and, when set, constrained server-side to 1.0-3.0 with
// decimals allowed -- see that module's docstring. `total` is just the sum
// of whichever fields are non-null (PlayerPoolPlayer.entry_total()), so a
// player scored on only 2 of the 6 fields still gets a meaningful total.
//
// game_environment is the *effective* value counted in `total` (an
// explicit override if one's been saved, otherwise whatever
// backend/services/game_environment/scoring.py's formula suggests from
// that game's Vegas-line data, otherwise null). game_environment_override
// is the raw saved override only (null if not overridden) -- the edit
// form should seed its input from *this* field, not from the blended
// game_environment, so leaving it blank and saving doesn't accidentally
// freeze in whatever the suggestion happened to be. game_environment_suggested
// is the formula's own output, shown as a hint.
export interface PlayerPoolPlayer {
  player: string;
  position: string;
  team: string;
  opponent: string;
  is_home: boolean | null;
  salary: number;
  ownership_pct: number | null;
  game_environment: number | null;
  game_environment_override: number | null;
  game_environment_suggested: number | null;
  game_matchup: number | null;
  ownership: number | null;
  volume: number | null;
  talent: number | null;
  salary_value: number | null;
  total: number;
}

// Body sent to PUT /api/player-pool/entry -- always the complete current
// set of fields from the edit form (a full replace of that player's saved
// week, not a partial patch -- see entries_repo.save_entry). Volume/Talent
// aren't here -- see PlayerAttributeEntryInput below.
export interface PlayerPoolEntryInput {
  season: number;
  week: number;
  player: string;
  game_environment: number | null;
  game_matchup: number | null;
  ownership: number | null;
  salary_value: number | null;
}

// Body sent to PUT /api/player-attributes/entry -- Volume/Talent, split
// into their own shared resource (see backend/schemas/player_attributes/
// player_attributes.py) since they're facts about the player that carry
// forward week to week, not re-entered fresh like Player Pool's own
// fields.
export interface PlayerAttributeEntryInput {
  season: number;
  week: number;
  player: string;
  volume: number | null;
  talent: number | null;
}

// Body sent to/returned from PUT /api/game-environment/entry -- one
// shared set of Vegas-line inputs per (season, week, game), not per
// player, reusable by any tab (not just Player Pool -- see
// backend/schemas/game_environment/game_environment.py).
export interface GameEnvironmentEntry {
  season: number;
  week: number;
  game_key: string;
  home_team: string;
  away_team: string;
  // Home team's line -- negative means favored, positive means
  // underdog. The away team's spread is just the negation of this.
  home_spread: number | null;
  over_under: number | null;
  home_implied_total: number | null;
  away_implied_total: number | null;
}

export interface PlayerPoolResult {
  players: PlayerPoolPlayer[];
  games: GameOption[];
  game_environment: GameEnvironmentEntry[];
}

// Mirrors backend/schemas/current_week/current_week.py -- the single
// (season, week) pointer shared across every weekly tab, set via one
// control in App.tsx rather than each tab keeping its own copy.
export interface CurrentWeek {
  season: number;
  week: number;
}

// Result of POST /api/ownership/upload-projections-csv -- the Settings
// tab's single-file ownership projections upload (offense + DST rows
// together -- see backend/services/ownership/csv_loader.py's
// parse_ownership_projections_csv). Separate from OwnershipImportResult
// above, which still backs the Ownership tab's own scrape-stand-in flow.
export interface OwnershipProjectionsImportResult {
  file_path: string;
  season: number;
  week: number;
  player_count: number;
  message_counts: Record<string, number>;
  messages: Message[];
}

// Result of POST /api/dk-salary/import-csv -- uploading DK's own native
// salary export, shared by Salary Blocks and Player Pool (see
// backend/services/dk_salary/dk_salary_loader.py). Same message shape as
// ScrapeResult/OwnershipImportResult above.
export interface DkSalaryImportResult {
  snapshot_path: string;
  scraped_at: string;
  season: number;
  week: number;
  player_count: number;
  message_counts: Record<string, number>;
  messages: Message[];
}

// Mirrors backend/schemas/player_selection/player_selection.py. `selected`
// is the computed state -- an explicit override if one's been saved for
// this player this week, else a position/salary default (see
// backend/services/player_selection/engine.py). DST never appears here --
// this feature doesn't apply to it.
export interface PlayerSelectionRow {
  player: string;
  position: string;
  team: string;
  salary: number;
  opponent: string;
  is_home: boolean | null;
  selected: boolean;
}

export interface PlayerSelectionResult {
  players: PlayerSelectionRow[];
}

// Body sent to PUT /api/player-selection/entry -- one player's explicit
// selected/unselected state for this (season, week, platform).
export interface PlayerSelectionEntryInput {
  season: number;
  week: number;
  platform: string;
  player: string;
  selected: boolean;
}

// Mirrors DkSalaryFileInfo (backend/api/dk_salary/file_info.py) and
// OwnershipProjectionsFileInfo (backend/api/ownership/projections_file_info.py)
// -- both are the same {filename, uploaded_at} shape, so one type covers
// both. Used by Settings to show "<filename> uploaded <timestamp>" as
// plain text instead of a clickable link (see FileUploadStatus.tsx).
export interface FileInfo {
  filename: string;
  uploaded_at: string;
}

// Mirrors backend/schemas/platform_settings/platform_settings.py -- the
// single (platform, contest) pair shared across every tab that touches a
// platform-specific file, set via one shared control in the Settings
// tab's top panel (see SettingsView.tsx) rather than each tab guessing.
// `platform` also determines the filename prefix used for this week's
// shared salary/ownership files (see backend/services/platform_settings/
// prefix.py) -- only "DraftKings" has a real file format behind it today.
export interface PlatformSettings {
  platform: string;
  contest: string;
}
