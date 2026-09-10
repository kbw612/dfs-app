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
  // depth-chart snapshot yet or this name didn't match one. Named
  // depth_rank (not rank) so it doesn't collide with the Player
  // Rankings tab's Total-based score, a wholly different concept.
  depth_rank: number | null;
  // Resolved Salary Multiplier * salary / 1000 (see backend/services/
  // salary_multiplier/engine.py) -- null everywhere OwnershipPlayer shows
  // up except Salary Blocks (the only view that resolves a platform's
  // multiplier before building these), same as the backend field's own
  // docstring (backend/schemas/ownership/ownership.py).
  expected_fpts: number | null;
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
  uploaded_at: string;
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
  // Sum of each player's own expected_fpts -- see OwnershipPlayer.expected_fpts.
  total_expected_fpts: number;
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

// Onslaught/Bring-back's own block shape (see backend/services/ownership/
// game_blocks.py's compute_game_blocks()) -- unlike PositionBlock, a
// GameBlock can mix positions (RB/WR/TE) and always spans both teams in
// one game. primary_team/primary_count is whichever side has more players
// in this block; bringback_team/bringback_count the other side (always
// 1-3, given the block's own 2-5 size range -- see that module's
// docstring for why). Onslaught and Bring-back share this exact shape;
// Bring-back's own view just additionally filters by bringback_count.
export interface GameBlock {
  players: OwnershipPlayer[];
  total_salary: number;
  total_expected_fpts: number;
  primary_team: string;
  primary_count: number;
  bringback_team: string;
  bringback_count: number;
}

export interface GameBlocksResult {
  blocks: GameBlock[];
  games: GameOption[];
  // Games left out of `blocks` because their own roster was too deep to
  // enumerate under the backend's safety cap (see game_blocks.py's
  // compute_game_blocks()) -- empty in the common case. Still worth
  // surfacing so it's clear why a specific matchup's blocks are missing
  // rather than looking like a silent gap.
  skipped_games: GameOption[];
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
// decimals allowed -- see that module's docstring. The one exception is
// game_environment (and its _override/_suggested siblings below), which is
// constrained to its own 0.0-1.0 range (0/0.5/1) instead, so it always
// carries less maximum weight in `total` than the other fields. `total` is
// just the sum of whichever fields are non-null (PlayerPoolPlayer.entry_total()),
// so a player scored on only 2 of the 6 fields still gets a meaningful total.
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
  // 1-indexed depth-chart rank (QB1/QB2, RB1-3, etc.) -- null if there's no
  // depth-chart snapshot yet or this player's name didn't match one (see
  // backend PlayerPoolPlayer.depth_rank's docstring). Used by SettingsView's
  // Player Default Factors grid to narrow to each position's top slots.
  // Named depth_rank (not rank) so it doesn't collide with the Player
  // Rankings tab's Total-based score, a wholly different concept.
  depth_rank: number | null;
  game_environment: number | null;
  game_environment_override: number | null;
  game_environment_suggested: number | null;
  game_matchup: number | null;
  ownership: number | null;
  volume: number | null;
  talent: number | null;
  salary_value: number | null;
  // Player Rankings' "Expected FPTS" column -- resolved Salary Multiplier
  // (Settings, or its computed default) times salary / 1000 -- see
  // backend/services/salary_multiplier/engine.py. Purely informational,
  // never included in `total`. Always a real number, for every position
  // including DST.
  expected_fpts: number;
  total: number;
}

// Body sent to PUT /api/player-pool/entry -- always the complete current
// set of fields from the edit form (a full replace of that player's saved
// week, not a partial patch -- see entries_repo.save_entry). Volume/Talent
// live here too -- no carry-forward from an earlier week; when a week has
// no explicit save, Player Pool falls back to the player's Player Default
// instead (see PlayerDefaultEntryInput below).
export interface PlayerPoolEntryInput {
  season: number;
  week: number;
  platform: string;
  player: string;
  game_environment: number | null;
  game_matchup: number | null;
  ownership: number | null;
  salary_value: number | null;
  volume: number | null;
  talent: number | null;
}

// Body sent to PUT /api/my-player-pool/entry -- see
// backend/schemas/my_player_pool/my_player_pool.py. My Player Pool is a
// personal, opt-in shortlist for feeding an external optimizer, fully
// independent of Settings' Player Selection narrowing -- a player can be
// in_pool=true here whether or not they're checked in Player Selection.
// GET /api/my-player-pool/latest reuses PlayerPoolResult directly (a My
// Player Pool row is exactly a Player Pool row, just drawn from this
// tab's own membership list), so there's no separate result type here.
export interface MyPlayerPoolEntryInput {
  season: number;
  week: number;
  platform: string;
  contest: string;
  player: string;
  in_pool: boolean;
}

// Body sent to PUT /api/player-defaults/entry -- a player's baseline
// Volume/Talent, set once per (season, player) in Settings' Player
// Default Settings grid (see backend/schemas/player_defaults/
// player_defaults.py). No `week` -- this isn't a per-week value, it's
// what Player Pool falls back to when a given week has no explicit save
// of its own.
//
// dfs_type is a separate, unrelated categorization tag on the same
// record (e.g. "Boom/Bust") -- see frontend/src/dfsTypes.ts for the
// selectable options and the Boom/Bust Players tab
// (components/BoomBustView.tsx) that reads it. null means no DFS Type
// set, same as volume/talent being null.
export interface PlayerDefaultEntryInput {
  season: number;
  player: string;
  volume: number | null;
  talent: number | null;
  dfs_type: string | null;
}

// GET /api/depth-charts/roster -- the latest depth-chart snapshot,
// flattened to one row per (team, position, depth_rank) for QB/RB/WR/TE
// across all 32 teams, independent of any week's DK salary file (see
// backend/schemas/depth_charts/roster.py). Settings' Player Default
// Factors grid uses this as its player universe instead of a week's
// Player Pool data, since a Default is set once per season and shouldn't
// depend on which teams happen to be on a given week's slate.
export interface DepthChartRosterPlayer {
  player: string;
  position: string;
  team: string;
  depth_rank: number;
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
  over_under: number | null;
  home_implied_total: number | null;
  away_implied_total: number | null;
}

export interface PlayerPoolResult {
  players: PlayerPoolPlayer[];
  games: GameOption[];
  game_environment: GameEnvironmentEntry[];
}

// Mirrors backend/schemas/vegas_lines/vegas_lines.py. `initial` is fixed
// as of the first scrape ever taken for this (season, week); `current` is
// whatever the most recent scrape found -- comparing the two is how the
// Vegas Lines tab shows line movement across the week. away_team/
// home_team/game_key are null when away_name/home_name didn't resolve to
// one of this app's team abbreviations (see backend/services/vegas_lines/
// scraper.py's alias table) -- the game still shows up, it just can't be
// applied to Game Environment yet.
export interface VegasLineValues {
  over_under: number | null;
  home_implied_total: number | null;
  away_implied_total: number | null;
}

export interface VegasLineGame {
  away_name: string;
  home_name: string;
  away_team: string | null;
  home_team: string | null;
  game_key: string | null;
  kickoff_label: string | null;
  initial: VegasLineValues;
  current: VegasLineValues;
}

export interface VegasLinesSnapshot {
  season: number;
  week: number;
  initial_scraped_at: string;
  current_scraped_at: string;
  games: VegasLineGame[];
}

// Response from POST /api/vegas-lines/scrape -- see backend/api/
// vegas_lines/scrape.py. `messages` covers any game block on the source
// page that couldn't be parsed (or whose team names didn't resolve --
// still included in the snapshot, just flagged here too).
export interface VegasLinesScrapeResult {
  snapshot: VegasLinesSnapshot;
  messages: string[];
}

// Response from POST /api/vegas-lines/apply -- see backend/api/
// vegas_lines/apply.py. Writes each resolved game's `current` values into
// that week's Game Environment scores; `messages` lists any game skipped
// for having unresolved team name(s).
export interface VegasLinesApplyResult {
  season: number;
  week: number;
  applied_count: number;
  skipped_count: number;
  messages: string[];
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

// OwnershipPlayer plus the *initial* ownership% -- see backend/schemas/
// ownership/ownership.py's OwnershipProjectionsPlayer. ownership_pct
// (inherited) is the current/latest upload's value, same as everywhere
// else in this app; initial_ownership_pct is None for a player who
// wasn't in the very first upload for this (season, week, platform).
export interface OwnershipProjectionsPlayer extends OwnershipPlayer {
  initial_ownership_pct: number | null;
}

// Result of GET /api/ownership/projections -- the parsed player list from
// whatever's currently uploaded via Settings' Ownership file (see
// backend/api/ownership/projections.py). Unlike OwnershipLatestResult
// (which reads the older mock-scrape/live-scrape OwnershipSnapshot),
// `players` here is exactly the rows in that uploaded CSV -- only whoever
// has a projected ownership% this week, nothing merged in from the DK
// salary file. Used by the Ownership Summary tab.
export interface OwnershipProjectionsResult {
  season: number;
  week: number;
  // On-disk modified time of the initial/current uploaded files
  // respectively -- equal for a (season, week, platform) that's only
  // ever been uploaded once. See backend/api/ownership/projections.py.
  initial_uploaded_at: string;
  current_uploaded_at: string;
  players: OwnershipProjectionsPlayer[];
}

// Result of GET /api/ownership/projections-file-info -- see
// backend/api/ownership/projections_file_info.py. Distinct from the
// generic FileInfo (used by DK Salary's own file-info endpoint), since
// only the Ownership file tracks a separate initial-upload timestamp.
export interface OwnershipProjectionsFileInfo {
  filename: string;
  uploaded_at: string;
  initial_uploaded_at: string;
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
// selected/unselected state for this (season, week, platform, contest).
export interface PlayerSelectionEntryInput {
  season: number;
  week: number;
  platform: string;
  contest: string;
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
// Scoped per season -- see backend/schemas/platform_settings/
// platform_settings.py.
export interface PlatformSettings {
  season: number;
  platform: string;
  contest: string;
}

// Mirrors backend/schemas/contest_results/contest_results.py -- one
// player/slot within a top-finishing lineup (see TopLineup). Any field
// can be null when this player's name didn't match the week's DK salary
// file and/or the contest export's own reference table -- see backend/
// services/contest_results/contest_results_engine.py's build_top_lineups
// for exactly when that happens (a real name mismatch, or the export's
// reference table simply not covering every player who appears in a
// top-N lineup -- see that module's own docstring).
export interface ContestLineupPlayer {
  roster_position: string;
  player: string;
  salary: number | null;
  position: string | null;
  pct_drafted: number | null;
  exp_pts: number | null;
  act_pts: number | null;
  diff: number | null;
  // 1 = most-owned/highest-scoring player at this player's own true
  // `position`, contest-wide (ownership aggregated across every roster
  // slot they were used in) -- null if `position` itself is unknown. See
  // backend/services/contest_results/contest_results_engine.py's
  // _build_player_rank_lookup.
  ownership_rank: number | null;
  points_rank: number | null;
  // "boom"/"bust" when Diff crosses the engine's fixed +/-5pt threshold,
  // null otherwise.
  boom_bust: "boom" | "bust" | null;
}

// One NFL game this lineup drew 2+ non-DST (QB/RB/WR/TE) players from --
// "onslaught" (both teams represented, split into the larger `primary`
// side and smaller `bringback` side, mirroring Salary Blocks' own
// Onslaught feature) or "overstack" (this feature's own term: 2+ players
// from ONE team, no bring-back at all -- bringback_team/positions are
// null/empty in that case).
export interface ContestGameStack {
  kind: "onslaught" | "overstack";
  primary_team: string;
  primary_positions: string[];
  bringback_team: string | null;
  bringback_positions: string[];
}

// Derived signals about one lineup's construction -- see
// contest_results_engine.py's _build_lineup_summary. Total lineup
// ownership isn't duplicated here -- see ContestTopLineup.total_pct_drafted.
export interface ContestLineupSummary {
  flex_position: string | null;
  game_stacks: ContestGameStack[];
  dst_team: string | null;
  dst_teammates: string[];
  dst_opponent_team: string | null;
  dst_opponent_positions: string[];
  qb_player: string | null;
  qb_stacked: boolean | null;
  distinct_games: number;
  distinct_teams: number;
  // $50,000 (DK Classic's cap) minus total_salary -- null if any player's
  // salary is unknown.
  salary_leftover: number | null;
}

// One contest entry's full 9-player lineup, in the export's own fixed
// slot order (DST, FLEX, QB, RB, RB, TE, WR, WR, WR). `points` is the
// entry's own reported total from the contest export -- total_act_pts
// (summed from `players`) should match it when every player resolved
// cleanly; see ContestLineupPlayer's own docstring for why it sometimes
// won't.
export interface ContestTopLineup {
  rank: number;
  entry_name: string;
  points: number;
  players: ContestLineupPlayer[];
  total_salary: number;
  total_pct_drafted: number;
  total_exp_pts: number;
  total_act_pts: number;
  total_diff: number;
  summary: ContestLineupSummary;
}

export interface ContestTopLineupsResult {
  lineups: ContestTopLineup[];
}

// One row of the contest export's own player-reference table (every
// distinct player+roster-slot combination that appeared anywhere in the
// contest), reformatted with Salary joined in from the week's DK salary
// file. Mirrors the dk_{contest}_contest_results_week{week}.csv shape --
// see backend/api/contest_results/player_results.py's docstring for why
// `contest` itself never appears here (a frontend-only export label).
export interface ContestResultRow {
  week: number;
  player: string;
  salary: number | null;
  roster_position: string;
  pct_drafted: number;
  fpts: number;
}

export interface ContestResultRowsResult {
  rows: ContestResultRow[];
}

// Result of POST /api/contest-results/import-csv -- see backend/api/
// contest_results/import_csv.py.
export interface ContestStandingsImportResult {
  snapshot_path: string;
  season: number;
  week: number;
  entry_count: number;
  reference_row_count: number;
}

// DK Players tab -- see backend/schemas/dk_players/dk_players.py. One row
// per player per week in the season-long tracker; unlike every other
// snapshot in this app, this isn't scoped to a single week.
export interface DkPlayerRow {
  name: string;
  position: string;
  roster_position: string;
  team: string;
  week: number;
  salary: number;
  pct_drafted: number;
  fpts: number;
  non_td_fpts: number;
  td_fpts: number;
}

export interface DkPlayersResult {
  season: number;
  platform: string;
  players: DkPlayerRow[];
}

// Checked before calling addDkPlayersWeek, so the "replace week N?"
// confirm dialog can be worded accurately -- see backend/api/dk_players/
// week_status.py.
export interface DkPlayersWeekStatus {
  week: number;
  exists: boolean;
  player_count: number;
  has_calculated_points: boolean;
}

export interface AddWeekPlayersResult {
  week: number;
  added_count: number;
  replaced: boolean;
}

// One tracker row that didn't match the stat file by exact name, but DOES
// have a close-spelling candidate in that file this week -- see
// backend/services/dk_players/dk_players_engine.py's
// suggest_stat_file_match. Worth adding a Name Alias for in Settings.
export interface PossibleStatNameMismatch {
  tracker_name: string;
  suggested_match: string;
}

export interface CalculateWeekPointsResult {
  week: number;
  updated_count: number;
  // Which of QB/RB/WR/TE have no stat file uploaded for this week at all
  // -- checked before name-matching, so a missing file shows up once here
  // instead of every one of that position's players individually
  // cluttering the two lists below.
  missing_stat_files: string[];
  // A stat-file miss is split in two: possible_stat_name_mismatches has a
  // close-spelling candidate in the stat file (probably needs a Name
  // Alias); no_stats_recorded has no candidate at all (probably this
  // player just didn't record a stat line that week -- inactive/injured/
  // bye) -- see backend/schemas/dk_players/dk_players.py's
  // CalculateWeekPointsResult for the full reasoning.
  possible_stat_name_mismatches: PossibleStatNameMismatch[];
  no_stats_recorded: string[];
  unmatched_contest_players: string[];
}

export type WeeklyStatsPosition = "QB" | "RB" | "WR" | "TE";

export interface WeeklyStatsImportResult {
  season: number;
  week: number;
  position: WeeklyStatsPosition;
  row_count: number;
}

export interface WeeklyStatsFileStatus {
  position: string;
  filename: string | null;
  uploaded_at: string | null;
}

export interface WeeklyStatsFileInfoResult {
  files: WeeklyStatsFileStatus[];
}

// Name Aliases -- see backend/schemas/name_aliases/name_aliases.py. Global
// list (not scoped to season/week/platform), maintained by hand in
// Settings and applied by DK Players' calculate-week-points to match
// names across the Salary File, weekly stat files, and Contest Standings.
export interface NameAlias {
  alias: string;
  canonical: string;
}

export interface NameAliasesResult {
  aliases: NameAlias[];
}

// Mirrors backend/schemas/salary_multiplier/salary_multiplier.py. Scoped
// to platform alone -- no season/week, since a multiplier isn't tied to
// either. `multiplier` is always the resolved value (an explicit override
// if saved, otherwise the computed default -- 4.0 for DraftKings, see
// backend/services/salary_multiplier/engine.py); `override` is the raw
// saved value only, null if this platform has never been explicitly set
// -- Settings seeds its input from `override`, not the blended
// `multiplier`, so an empty input reads as "using the default" rather
// than freezing in whatever that default happened to resolve to.
export interface SalaryMultiplierResult {
  platform: string;
  multiplier: number;
  override: number | null;
}

// Body sent to PUT /api/salary-multiplier/entry. multiplier: null clears
// the override back to the computed default.
export interface SalaryMultiplierEntryInput {
  platform: string;
  multiplier: number | null;
}
