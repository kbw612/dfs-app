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

// Mirrors backend/schemas/depth_charts/snapshot.py's Player/Team/Snapshot
// exactly -- the full current depth chart (every position, every player's
// status), unlike DepthChartRosterPlayer below (a flattened offense-only
// view built for a different purpose -- Settings' Player Default Factors
// grid). Backs GET /api/depth-charts/latest, which the Depth Charts tab
// reads from -- see DepthChartsView.tsx.
export interface DepthChartPlayer {
  player: string;
  status: string | null;
}

export interface DepthChartTeam {
  team_abbrev: string | null;
  team_name: string;
  defensive_formation: string | null;
  positions: Record<string, DepthChartPlayer[]>;
}

export interface DepthChartSnapshot {
  scraped_at: string;
  source_url: string;
  messages: Message[];
  teams: DepthChartTeam[];
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
  // cap - cheapest_dst_salary_this_contest -- every block in `blocks`
  // already has total_salary <= this (see the backend's
  // filter_blocks_by_max_salary), same rule as Onslaught's own
  // max_onslaught_salary. null only when this contest's own salary file
  // has no DST rows at all (the cap isn't applied then).
  max_block_salary: number | null;
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
  // cap - cheapest_dst_salary_this_contest -- every block in `blocks`
  // already has total_salary <= this (see the backend's
  // filter_game_blocks_by_max_salary), surfaced here purely so this view
  // can explain the cap in its own hint text rather than silently
  // returning fewer blocks. null only when this contest's own salary file
  // has no DST rows at all (the cap isn't applied then).
  max_onslaught_salary: number | null;
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
// decimals allowed -- see that module's docstring. game_environment (and
// its _override/_suggested siblings below) shares this same range -- it
// used to be constrained to its own smaller 0.0-1.0 scale, which gave it
// less maximum weight in `total` than the other fields, but that's no
// longer the case. `total` is just the sum of whichever fields are
// non-null (PlayerPoolPlayer.entry_total()), so a player scored on only 2
// of the 6 fields still gets a meaningful total.
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
  // DST-only -- the effective value counted in `total` (an explicit
  // override if saved this week, otherwise score_weather_color()'s own
  // suggestion from that DST's game's Weather note, defaulting to a
  // neutral 2.0 with no notable weather this week). See backend
  // PlayerPoolPlayer.weather's docstring.
  weather: number | null;
  // The *effective* value -- this week's explicit override if saved,
  // otherwise whether "Standalone" is one of this player's Settings
  // Default dfs_types, otherwise false (see backend
  // PlayerPoolPlayer.standalone's docstring). Null unconditionally for
  // DST (not applicable); always a real true/false for QB/RB/WR/TE. Not
  // part of `total` -- purely a tag for a future lineup-optimizer
  // validator that flags a non-Standalone player rostered with nobody
  // else from their own game.
  standalone: boolean | null;
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
  weather: number | null;
  volume: number | null;
  talent: number | null;
  // Override only, QB/RB/WR/TE only -- see backend
  // PlayerPoolEntry.standalone's docstring. Null here means "no explicit
  // save for this exact week," falling back at read time to the player's
  // Settings Default dfs_types, then to false.
  standalone: boolean | null;
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
// dfs_types is a separate, unrelated set of categorization tags on the
// same record (e.g. "Boom/Bust", "Standalone") -- see
// frontend/src/dfsTypes.ts for the selectable options, the Boom/Bust
// Players tab (components/BoomBustView.tsx) that reads the Boom/Bust tag,
// and Player Pool's standalone field that derives its own default from
// the Standalone tag. A player can carry any combination of tags at
// once; an empty list means no DFS Type set, same as volume/talent being
// null.
export interface PlayerDefaultEntryInput {
  season: number;
  player: string;
  volume: number | null;
  talent: number | null;
  dfs_types: string[];
}

// Body sent to/from PUT /api/team-factors/entry and returned by GET
// /api/team-factors/latest -- Settings' Team Default Factors grid (see
// backend/schemas/team_factors/team_factors.py). Keyed by (season, team,
// position) rather than by player: "how tough is this team's defense
// against this offensive position." No `week` -- same "set once per
// season, not per week" shape as PlayerDefaultEntryInput above. Player
// Pool's Matchup field falls back to the *opponent's* saved factor at a
// player's own position when that week has no explicit Matchup save of
// its own (see backend/services/player_pool/engine.py's
// _resolve_team_factor_default). factor is null when this (team,
// position) pair has never been explicitly set -- Player Pool then falls
// through to the flat 2.0 neutral, same as an unset Player Default.
export interface TeamFactorEntryInput {
  season: number;
  team: string;
  position: string;
  factor: number | null;
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

// GET/PUT /api/usage-bump-players -- the hand-curated Usage Bump Players
// list (backend/schemas/usage_bump/usage_bump_players.py), edited from
// the Usage Bump Players tab. Field names are camelCase to match the
// file's own on-disk keys exactly (see that schema's own docstring).
// `moreUsagePlayers` is priority-ordered -- first name is the biggest
// beneficiary.
export interface UsageBumpPlayerEntry {
  name: string;
  moreUsagePlayers: string[];
}

export interface UsageBumpTeamEntry {
  teamAbbrev: string;
  players: UsageBumpPlayerEntry[];
}

export interface UsageBumpPlayersResult {
  teams: UsageBumpTeamEntry[];
}

// GET /api/star-players/latest, PUT /api/star-players/entry -- the
// hand-curated "this player is a difference-maker" flag (backend/schemas/
// star_players/star_players.py), set from the Depth Charts tab's star
// icon at any position, not just skill positions that already have their
// own Player Pool scoring. Keyed by (team, player), same rationale as
// UsageBumpTeamEntry's own teamAbbrev keying -- the depth-chart snapshot
// matches players by name only, so two same-named players on different
// teams would otherwise collide.
export interface StarPlayerEntry {
  team: string;
  player: string;
}

export interface StarPlayersResult {
  players: StarPlayerEntry[];
}

// Body sent to PUT /api/star-players/entry -- distinct from StarPlayerEntry
// above (the response list's shape, where presence alone means "starred")
// since setting the flag needs an explicit target state to request.
export interface StarPlayerEntryInput {
  team: string;
  player: string;
  starred: boolean;
}

// Injury Report (backend/schemas/injury_report/injury_report.py) -- every
// player from the latest Depth Charts snapshot who currently carries a
// non-null status, grouped by this week's game matchup. `starred` is
// already joined in server-side from Star Players, since this tab is
// read-only display (no star-toggle control of its own).
export interface InjuryPlayerEntry {
  team: string;
  player: string;
  position: string;
  status: string;
  starred: boolean;
  // 1-based index within this player's own position's depth-chart array
  // (e.g. 1 = starter). Powers the Position Depth chip filter.
  depth: number;
}

export interface InjuryGameGroup {
  key: string;
  label: string;
  teams: string[];
  players: InjuryPlayerEntry[];
}

export interface InjuryReportResult {
  scraped_at: string;
  week: number;
  games: InjuryGameGroup[];
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

// away_team/home_team/game_key are null when away_name/home_name didn't
// resolve to one of this app's team abbreviations (see backend/services/
// weather/scraper.py) -- the note still shows up, it just can't be tied
// to a specific game_key. `color` is whatever raw color word the source
// site used (e.g. "yellow", "orange", "green", "red") -- passed through
// as-is rather than mapped to a fixed set, since new colors may appear.
export interface WeatherGame {
  away_name: string;
  home_name: string;
  away_team: string | null;
  home_team: string | null;
  game_key: string | null;
  kickoff_label: string | null;
  color: string;
  note: string;
}

export interface WeatherSnapshot {
  season: number;
  week: number;
  scraped_at: string;
  games: WeatherGame[];
}

// Response from POST /api/weather/scrape -- see backend/api/weather/
// scrape.py. `messages` covers any note card on the source page that
// couldn't be parsed (or whose team names didn't resolve -- still
// included in the snapshot, just flagged here too).
export interface WeatherScrapeResult {
  snapshot: WeatherSnapshot;
  messages: string[];
}

// Response from POST /api/player-pool/calculate-ownership-scores -- see
// backend/api/player_pool/calculate_ownership_scores.py. Bulk-saves each
// player's Ownership score computed from their current ownership_pct;
// `skipped_count` covers DST (Ownership doesn't apply) and any player
// with no ownership_pct to score off of.
export interface OwnershipScoresApplyResult {
  season: number;
  week: number;
  applied_count: number;
  skipped_count: number;
}

// See backend/api/player_pool/calculate_weather_scores.py -- Player
// Rankings' DST-only Weather refresh icon.
export interface WeatherScoresApplyResult {
  season: number;
  week: number;
  applied_count: number;
  skipped_count: number;
}

// See backend/api/player_pool/reset_matchup.py -- Player Rankings' DST
// Matchup refresh icon. reset_count is how many DSTs actually had an
// explicit Matchup override cleared (a DST with no override to begin with
// isn't counted).
export interface MatchupResetResult {
  season: number;
  week: number;
  position: string;
  reset_count: number;
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

// Result of scraping OneWeekSeason's DraftKings Main Slate page -- same
// shape as OwnershipProjectionsImportResult above (it saves through the
// exact same file), just from a scrape instead of a manual file upload.
export type OwnershipMainSlateScrapeResult = OwnershipProjectionsImportResult;

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

// Mirrors backend/schemas/ownership/ownership_summary.py -- backend-
// computed team/game ownership rollups for the Ownership Summary tab (see
// backend/services/ownership/ownership_summary.py's own docstring for why
// this moved server-side instead of being computed here in the frontend).
// actual_total_ownership_pct is null (not 0) when no Contest Standings are
// uploaded yet for this (season, week, platform, contest) -- distinct
// from a real 0% total, same convention as everywhere else in this app.
export interface TeamOwnershipRollup {
  team: string;
  initial_total_ownership_pct: number;
  total_ownership_pct: number;
  actual_total_ownership_pct: number | null;
}

export interface GameOwnershipRollup {
  key: string;
  label: string;
  away_team: string | null;
  home_team: string | null;
  initial_total_ownership_pct: number;
  total_ownership_pct: number;
  actual_total_ownership_pct: number | null;
  // Every player in the game (any position, including DST), sorted by
  // ownership_pct descending -- backs this tab's own per-game detail
  // expand.
  players: OwnershipProjectionsPlayer[];
}

export interface OwnershipSummaryResult {
  teams: TeamOwnershipRollup[];
  games: GameOwnershipRollup[];
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

// One row of the contest export's own player-reference table, collapsed
// to one row per PLAYER -- %Drafted summed across every roster slot they
// were used in (DK's own export tracks a flex-eligible player's RB and
// FLEX usage as two separate, individually-smaller rows -- see backend/
// schemas/contest_results/contest_results.py's own ContestResultRow
// docstring for why that reads as confusing shown as-is). `position` is
// the player's true position (QB/RB/WR/TE/DST) from the DK salary file,
// never "FLEX" -- null if their name didn't match anything there.
// Reformatted with Salary joined in from the week's DK salary file.
// Mirrors the dk_{contest}_contest_results_week{week}.csv shape -- see
// backend/api/contest_results/player_results.py's docstring for why
// `contest` itself never appears here (a frontend-only export label).
export interface ContestResultRow {
  week: number;
  player: string;
  salary: number | null;
  position: string | null;
  pct_drafted: number;
  fpts: number;
}

// One slot in an OptimalLineup -- unlike ContestLineupPlayer above, every
// field here is a plain non-optional value; see backend/services/
// contest_results/optimal_lineup.py -- a player only makes it into an
// OptimalLineup if they had a real salary and true position to begin
// with.
export interface OptimalLineupPlayer {
  roster_position: string;
  player: string;
  position: string;
  salary: number;
  fpts: number;
}

// The single highest actual-FPTS DK Classic lineup (1 QB, 2 RB, 3 WR, 1
// TE, 1 FLEX, 1 DST) buildable under a salary cap, computed from this
// week's own Contest results player list -- "if you'd known the real
// scores in advance, what's the best possible lineup." See backend/
// services/contest_results/optimal_lineup.py's own docstring for how
// it's solved and its player-pool coverage caveat (only players someone
// actually rostered in the contest are eligible).
export interface OptimalLineup {
  players: OptimalLineupPlayer[];
  total_salary: number;
  total_fpts: number;
  salary_leftover: number;
}

export interface ContestResultRowsResult {
  rows: ContestResultRow[];
}

// A pool of the 10 exact highest-scoring distinct (not real-contest-
// entry) OptimalLineups -- see backend/services/contest_results/
// lineup_generators.py's build_top10_by_points for the generation
// algorithm, behind fetchOptimalLineupsTop10. Cached to a JSON file on
// the backend the first time it's generated for a given week -- see
// backend/repositories/contest_results/optimal_lineups_cache_repo.py --
// so a later page visit just reads that file back instead of
// regenerating.
export interface OptimalLineupsResult {
  lineups: OptimalLineup[];
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

export interface WeeklyStatsFileStatus {
  position: string;
  // Season-long file's own name (e.g. "FantasyData_QBs.csv"), present
  // once ANY week has ever been saved for this position.
  filename: string | null;
  // Season file's on-disk mtime -- last time ANY week was saved to it,
  // not necessarily the currently-selected week's.
  uploaded_at: string | null;
  // Whether the currently-selected week specifically already has rows in
  // the season file -- this is what should gate an overwrite warning.
  week_has_data: boolean;
}

export interface WeeklyStatsFileInfoResult {
  files: WeeklyStatsFileStatus[];
}

export interface WeeklyStatsScrapePositionResult {
  position: string;
  row_count: number | null;
  error: string | null;
}

export interface WeeklyStatsScrapeResult {
  season: number;
  week: number;
  results: WeeklyStatsScrapePositionResult[];
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

// Mirrors backend/api/schedule/import_csv.py's response -- the full-
// season Team/Week/Opponent/GameLocation schedule upload, one file per
// season (see FileInfo above for the matching file-info shape, reused
// as-is since Schedule's status has the same {filename, uploaded_at}
// shape as every other upload).
export interface ScheduleImportResult {
  season: number;
  row_count: number;
}

// Mirrors backend/schemas/game_logs/game_logs.py exactly.
export interface GameLogRow {
  week: number;
  name: string;
  position: string;
  team: string;
  salary: number;
  opponent: string | null;
  game_location: "Home" | "Away" | "BYE" | null;
  multiplier: number | null;
  fpts: number;
  non_td_fpts: number;
  non_td_fpts_pct: number | null;
  td_fpts: number;
  td_fpts_pct: number | null;
  touches: number | null;
  targets: number | null;
  receptions: number | null;
  receiving_yards: number | null;
  rec_td: number | null;
  rush_att: number | null;
  rush_yards: number | null;
  rush_td: number | null;
  // TGTSHARE/TOUCHSHARE/OPPSHARE -- see backend's usage_shares.py for the
  // exact formula each one uses. All three null when the underlying team
  // total is unavailable; target_share_pct is additionally null for QB
  // (no FantasyData file carries a QB's own targets), while touch_share_pct
  // and opp_share_pct stay meaningful (carries-only) for a QB instead.
  target_share_pct: number | null;
  touch_share_pct: number | null;
  opp_share_pct: number | null;
  // QB's own passing line -- always null for every other position, same
  // "not applicable" convention as the usage fields above.
  pass_cmp: number | null;
  pass_att: number | null;
  pass_cmp_pct: number | null;
  pass_yds: number | null;
  pass_avg: number | null;
  pass_td: number | null;
  pass_int: number | null;
  pass_sck: number | null;
  pass_rtg: number | null;
  // Background-color tier for this one week's raw pass_att/pass_yds value
  // -- "low"/"high" once it crosses the red/green threshold, null
  // otherwise (in between, or pass_att/pass_yds itself being null).
  // Computed server-side (same shared thresholds as TeamStatSummaryRow's
  // own average_tier/median_tier for these two stats, see backend/
  // services/game_logs/game_logs_engine.py's tier_for_stat_value) --
  // deliberately not present for rush_att/rush_yards/receptions/
  // receiving_yards, which keep their own unrelated top-2-share shading
  // computed client-side (see gameLogsShared.ts's shareRankClassName).
  pass_att_tier: "low" | "high" | null;
  pass_yds_tier: "low" | "high" | null;
  // DST's own sacks recorded -- always null for every other position, and
  // deliberately separate from pass_sck (that's sacks *taken* by a QB).
  sacks: number | null;
}

export interface GameOption {
  key: string;
  label: string;
  teams: string[];
}

// A team's own average/median for one counting stat, over whatever
// `games` the owning TeamStatSummaryRow actually covers -- both null when
// every one of that team's weeks had this stat's team total as null (e.g.
// Pass Yds on a week its QB row wasn't found), never a silent 0. Computed
// server-side (backend/services/game_logs/game_logs_engine.py's
// build_team_stat_summary) -- the frontend only renders these, it never
// computes them.
export interface StatAverage {
  average: number | null;
  median: number | null;
  // Background-color tier for `average`/`median` respectively -- "low"/
  // "high" for one of the 4 stats with defined red/green thresholds
  // (Pass Att, Pass Yds, Rush Att, Rush Yds) once that value crosses one,
  // null otherwise (in between the thresholds, or a stat with none
  // defined at all -- Rec TD, Rush TD, Pass TD -- or the value itself
  // being null). See backend/services/game_logs/game_logs_engine.py's
  // tier_for_stat_value, the single shared thresholds table.
  average_tier: "low" | "high" | null;
  median_tier: "low" | "high" | null;
}

// One TEAM's own Average/Median summary over Rec TD/Rush Att/Rush Yds/
// Rush TD/Pass Att/Pass Yds/Pass TD -- every currently-shown player's own
// value is summed into a team-week total first, and this row's average/
// median are computed across those per-week team totals, across exactly
// the weeks already shown in `rows`
// (GameLogsResult/GameLogsAgainstResult's own `week`/`lookback_weeks` are
// NOT the same as this row's `games` -- that's the number of weeks
// actually summed, which can be fewer than the lookback window). `team`
// is the roster team itself for Game Logs, or the "Against {team}"
// panel's own team for Game Logs Against. Receptions/Receiving Yards
// were dropped from this summary at the person's own request -- they're
// still on every per-week GameLogRow/GameLogAgainstRow, just not
// summarized here.
export interface TeamStatSummaryRow {
  team: string;
  games: number;
  rec_td: StatAverage;
  rush_att: StatAverage;
  rush_yards: StatAverage;
  rush_td: StatAverage;
  pass_att: StatAverage;
  pass_yds: StatAverage;
  pass_td: StatAverage;
}

export interface GameLogsResult {
  season: number;
  week: number;
  reference_week: number;
  lookback_weeks: number;
  games: GameOption[];
  rows: GameLogRow[];
  team_stat_summary: TeamStatSummaryRow[];
}

// Mirrors backend/schemas/multipliers/multipliers.py's TrailingMultiplier --
// one prior week's own Multiplier, pivoted onto the base week's row instead
// of appearing as its own row (unlike Game Logs). `multiplier` is null when
// that player has no tracker row at all for `week` (bye, not yet rostered,
// tracker not backfilled that far) -- same "no data" convention as every
// other nullable field in this app, not a real 0.
export interface TrailingMultiplier {
  week: number;
  multiplier: number | null;
  // Same fpts/(salary/1000) formula as `multiplier`, run against
  // non_td_fpts instead -- feeds the Breakout Watch panel's non-TD
  // multiplier trend without needing this week's own salary client-side.
  non_td_multiplier: number | null;
  // This week's own TD FPTS -- null only when there's no tracker row for
  // this week at all. Lets Breakout Watch apply its "a week with a
  // touchdown doesn't count as high" rule to trailing weeks, not just the
  // base week (see MultiplierRow.td_fpts for the base week's equivalent).
  td_fpts: number | null;
}

// Mirrors backend/schemas/multipliers/multipliers.py's MultiplierRow exactly
// -- the Multipliers tab's row shape. One row per rostered player: the base
// week's own box score (same fields as GameLogRow's own Salary/Opponent/
// Multiplier/FPTS/Non-TD/TD set) plus `trailing`, always exactly
// `trailing_weeks` entries long, one per week working backwards from
// `base_week - 1`.
export interface MultiplierRow {
  name: string;
  position: string;
  team: string;
  week: number;
  salary: number;
  opponent: string | null;
  game_location: "Home" | "Away" | "BYE" | null;
  multiplier: number | null;
  non_td_multiplier: number | null;
  fpts: number;
  non_td_fpts: number;
  non_td_fpts_pct: number | null;
  td_fpts: number;
  td_fpts_pct: number | null;
  trailing: TrailingMultiplier[];
}

// Mirrors backend/schemas/multipliers/multipliers.py's MultipliersResult.
// `base_week` is always `week - 1` -- see the backend engine's own
// docstring for why this tab is always strictly "last week's review," not
// tied to whichever week is currently reference-scoped elsewhere. `games`
// is built from the base week's own schedule (see build_multiplier_rows),
// same reused GameOption shape as Game Logs/Game Logs Against.
export interface MultipliersResult {
  season: number;
  week: number;
  base_week: number;
  trailing_weeks: number;
  games: GameOption[];
  rows: MultiplierRow[];
}

// Mirrors backend/schemas/dst_trends/dst_trends.py's DstTrendTeamRow --
// one row per team, in either the DST Trends tab's "Forcing" leaderboard
// (this team's own DST sacks/takeaways generated) or its "Allowing"
// leaderboard (the SAME fields, but summed from opponents' DST rows that
// had this team as their own OPP that week -- sacks/turnovers given up by
// this team's offense). See DstTrendsResult's own forcing/allowing split.
export interface DstTrendTeamRow {
  team: string;
  games: number;
  sacks: number;
  sacks_per_game: number;
  takeaways: number;
  takeaways_per_game: number;
}

// Mirrors backend/schemas/dst_trends/dst_trends.py's DstTrendsResult.
// `through_week` is always `week - 1` -- same "review the most recently
// completed week" convention as Multipliers' own base_week.
export interface DstTrendsResult {
  season: number;
  week: number;
  through_week: number;
  window_weeks: number;
  forcing: DstTrendTeamRow[];
  allowing: DstTrendTeamRow[];
}

// Mirrors backend/schemas/game_preview/game_preview.py exactly. Every
// field on GamePreviewVegas/GamePreviewWeather/GamePreviewDstMatchup can
// be independently absent -- see that module's own per-field docstrings
// for why (not yet scraped, no matching game_key, week 1, etc.) -- render
// each piece defensively rather than assuming the whole object is present
// just because the game itself is.
export interface GamePreviewVegas {
  over_under: number | null;
  away_implied_total: number | null;
  home_implied_total: number | null;
  kickoff_label: string | null;
}

export interface GamePreviewWeather {
  color: string;
  note: string;
}

export interface GamePreviewTeamFactors {
  qb: number | null;
  rb: number | null;
  wr: number | null;
  te: number | null;
  dst: number | null;
}

export interface GamePreviewDstMatchup {
  games: number;
  sacks_per_game_forced: number;
  takeaways_per_game_forced: number;
  opponent_sacks_per_game_allowed: number;
  opponent_takeaways_per_game_allowed: number;
}

// Phase B -- one fired signal on a player, with a plain-English reason.
// "leverage"/"chalk" are ownership-only signals (not narrated in the
// game's own `narrative_sections` -- see game_preview_narrative.py) but
// still shown on the player's own tag list.
export type GamePreviewTagKind = "play" | "fade" | "monitor" | "leverage" | "chalk";

export interface GamePreviewPlayerTag {
  kind: GamePreviewTagKind;
  reason: string;
}

// Only players with >=1 fired tag appear here at all -- see
// GamePreviewPlayer's own backend docstring ("no signal, no row").
export interface GamePreviewPlayer {
  name: string;
  position: string;
  team: string;
  // 1-indexed depth-chart rank (e.g. 1 for a starting WR1, 4 for a WR4) --
  // null when no depth-chart snapshot was available or this name didn't
  // match anyone on it.
  depth: number | null;
  tags: GamePreviewPlayerTag[];
}

// Phase D -- one player-level row inside an injury group. `starred`
// mirrors Star Players' own flag -- rendered as a gold star next to the
// name (same convention as Depth Charts/Injury Report), not as a
// separate group of its own.
export interface GamePreviewInjuryEntry {
  player: string;
  position: string;
  depth: number;
  status: string;
  starred: boolean;
}

// One group's worth of injury entries (e.g. every Offensive Line player
// at depth 1 who has a status this week) -- `label` is the display
// heading ("O-Line (depth 1)", etc.). Only groups with >=1 entry appear
// in GamePreviewTeamSide.injury_groups at all.
export interface GamePreviewInjuryGroup {
  label: string;
  entries: GamePreviewInjuryEntry[];
}

// Phase C -- one section of the auto-generated summary. `label` is null
// for the standalone Vegas line (rendered as a single flat bullet with
// no heading) and set for every other section ("O vs D Line Matchup",
// "Pace", "Matchup Trends", "Ownership", "Plays to consider", "Fade",
// "Monitor") -- rendered as a heading followed by its own nested bullet
// list.
export interface GamePreviewNarrativeSection {
  label: string | null;
  entries: string[];
}

// One played week's worth of a team's own offensive pace -- an entry in
// GamePreviewPaceTrend.trailing, used to render a weeks-as-columns trend
// table (the "weeks to show" input controls how many entries land here).
export interface GamePreviewPaceWeek {
  week: number;
  // This team's own opponent that week, from the Schedule file -- null
  // when no Schedule file covers that team/week.
  opponent: string | null;
  // "home" or "away" -- this team's own side of that week's game, from the
  // Schedule file's own GameLocation column, so the UI can render "vs DEN"
  // (home) vs. "@ DEN" (away) instead of a location-blind "vs". Null under
  // the exact same condition as `opponent` (no Schedule coverage).
  opponent_location: "home" | "away" | null;
  plays: number;
  pass_att: number;
  rush_att: number;
  pass_rate_pct: number | null;
  rush_rate_pct: number | null;
  // vs. the played week immediately before THIS one (not the parent
  // GamePreviewPaceTrend's own top-level "most recent" comparison) -- null
  // for the oldest week in `trailing` when there's no earlier played week
  // to diff against.
  plays_delta: number | null;
  pass_rate_delta: number | null;
  rush_rate_delta: number | null;
}

// This team's own most-recent-played-week pace snapshot (week/plays/rates
// plus a one-step delta vs. the week before it), plus `trailing` -- up to
// window_weeks played weeks of the same numbers, newest first, for a
// multi-week table. Null when this team has no played week with any stat
// line yet (week 1, or no weekly stats uploaded).
export interface GamePreviewPaceTrend {
  week: number;
  plays: number;
  pass_att: number;
  rush_att: number;
  pass_rate_pct: number | null;
  rush_rate_pct: number | null;
  plays_delta: number | null;
  pass_rate_delta: number | null;
  trailing: GamePreviewPaceWeek[];
}

export interface GamePreviewTeamSide {
  team: string;
  is_home: boolean;
  team_factors: GamePreviewTeamFactors;
  dst_matchup: GamePreviewDstMatchup | null;
  pace_trend: GamePreviewPaceTrend | null;
  players: GamePreviewPlayer[];
  // Phase D -- this team's own injury summary, one group per position
  // bucket (O-Line/Defensive Front/Defensive Backs depth 1, Skill
  // positions depth 1-4) -- see game_preview_injuries.py. A starred
  // player shows a gold star on their own entry rather than getting a
  // separate group. Empty when there's nothing notable, or no
  // depth-chart snapshot at all.
  injury_groups: GamePreviewInjuryGroup[];
  // Sum of ownership_pct across this team's own rostered QB/RB/WR/TE rows
  // (DST excluded) -- same rule as Ownership Summary's own
  // computeTeamOwnership(). Null when there's no ownership data at all for
  // this team this week -- see backend GamePreviewTeamSide.projected_ownership_pct's
  // own docstring.
  projected_ownership_pct: number | null;
  // This team's own Rush/Pass Att/Yds/TD + Rec TD average/median over the
  // trailing window -- same TeamStatSummaryRow shape (and the same
  // average_tier/median_tier red/green thresholds) as Game Logs' own
  // Team Summary (Avg / Median) section. Null under the same "no stat
  // lines in the window yet" condition as pace_trend being null.
  stat_summary: TeamStatSummaryRow | null;
  // Two INDEPENDENT tiers, not a mutually-exclusive pick -- a team can be
  // "high" on run volume AND "low" on pass volume (or any other
  // combination) at once. Derived from stat_summary's own tiers (see
  // backend GamePreviewTeamSide.run_volume_tier/pass_volume_tier's own
  // docstring). Both null can mean either "no data at all" (stat_summary
  // itself is null) or "genuinely normal on both sides" (stat_summary
  // exists, neither stat tripped a threshold) -- check stat_summary
  // directly to tell those apart (see TeamStatSummaryColumn's own usage).
  run_volume_tier: "low" | "high" | null;
  pass_volume_tier: "low" | "high" | null;
}

export interface GamePreviewGame {
  key: string;
  label: string;
  teams: string[];
  vegas: GamePreviewVegas | null;
  weather: GamePreviewWeather | null;
  away: GamePreviewTeamSide;
  home: GamePreviewTeamSide;
  // Phase C -- a handful of deterministic, rule-based sections combining
  // this game's own context above with its players' own tags. Weather is
  // NOT one of these -- see `weather` above, rendered as its own
  // dedicated line. Always non-empty (see build_game_narrative's own
  // docstring for the no-signal fallback section).
  narrative_sections: GamePreviewNarrativeSection[];
  // away.projected_ownership_pct + home.projected_ownership_pct -- null
  // when neither side has ownership data this week.
  combined_projected_ownership_pct: number | null;
  // combined_projected_ownership_pct / vegas.over_under -- lower means a
  // comparable scoring environment at a lower combined ownership cost. Null
  // when either input is missing (or over_under is 0).
  total_to_ownership_ratio: number | null;
  // vegas.over_under >= 47.0 -- surfaced so the frontend can highlight a
  // high-total game without re-deriving the threshold. Always false when
  // vegas or vegas.over_under is null.
  high_over_under: boolean;
  // vegas.over_under < 40.0 -- the low-total mirror of high_over_under
  // above, same reasoning. Never true at the same time as high_over_under
  // (the two thresholds don't overlap).
  low_over_under: boolean;
}

export interface GamePreviewResult {
  season: number;
  week: number;
  through_week: number;
  window_weeks: number;
  games: GamePreviewGame[];
}

// Mirrors backend/schemas/game_logs/game_logs_against.py exactly -- the
// Game Logs Against tab's row shape. Still no raw Touches/Targets/etc.
// (unlike GameLogRow) and no `team`/`opponent` display columns --
// `against_team` is only for grouping/filtering, the panel heading
// ("Against {team}") already says which team this row's player faced.
// target_share_pct/touch_share_pct/opp_share_pct and the Pass fields ARE
// the same as GameLogRow's own, though -- same null-when conditions, see
// there.
export interface GameLogAgainstRow {
  against_team: string;
  week: number;
  name: string;
  position: string;
  salary: number;
  game_location: "Home" | "Away" | "BYE" | null;
  multiplier: number | null;
  fpts: number;
  non_td_fpts: number;
  non_td_fpts_pct: number | null;
  td_fpts: number;
  td_fpts_pct: number | null;
  touches: number | null;
  targets: number | null;
  receptions: number | null;
  receiving_yards: number | null;
  rec_td: number | null;
  rush_att: number | null;
  rush_yards: number | null;
  rush_td: number | null;
  target_share_pct: number | null;
  touch_share_pct: number | null;
  opp_share_pct: number | null;
  pass_cmp: number | null;
  pass_att: number | null;
  pass_cmp_pct: number | null;
  pass_yds: number | null;
  pass_avg: number | null;
  pass_td: number | null;
  pass_int: number | null;
  pass_sck: number | null;
  pass_rtg: number | null;
  // Same field/convention as GameLogRow's own pass_att_tier/pass_yds_tier.
  pass_att_tier: "low" | "high" | null;
  pass_yds_tier: "low" | "high" | null;
  sacks: number | null;
}

export interface GameLogsAgainstResult {
  season: number;
  week: number;
  lookback_weeks: number;
  games: GameOption[];
  rows: GameLogAgainstRow[];
  // Same shape as GameLogsResult's own (see TeamStatSummaryRow) -- `team`
  // on each entry holds `against_team` here instead of a rostered
  // player's real team.
  team_stat_summary: TeamStatSummaryRow[];
}

// Lineup Scenarios -- mirrors backend/schemas/lineup_scenarios/
// lineup_scenarios.py exactly (see that module's docstring for the full
// feature shape: upload a batch of externally-built lineups, define
// team-stack scenarios, see which lineups satisfy which scenarios).
export interface ScheduleGamesResult {
  season: number;
  week: number;
  games: GameOption[];
}

export interface LineupScenarioUploadResult {
  lineup_count: number;
  roster_positions: string[];
}

export interface UploadedLineupPlayer {
  roster_position: string;
  name: string;
  team: string | null;
  // This player's own real NFL position (QB/RB/WR/TE/DST), resolved from
  // the DK salary snapshot -- distinct from roster_position, which can be
  // an ambiguous "FLEX" slot. null whenever `team` is also null.
  position: string | null;
  // This player's own depth-chart slot, e.g. "RB1", "WR2" -- resolved from
  // the latest depth chart snapshot. This, not the coarser `position`
  // above, is what a scenario team flag's own `positions` filter actually
  // checks. DST always resolves to the literal "DST" (no ranked depth).
  // null whenever `team` is unresolved, the position isn't depth-tracked,
  // or no depth-chart snapshot has been scraped yet.
  depth_slot: string | null;
}

export interface UploadedLineup {
  index: number;
  players: UploadedLineupPlayer[];
}

// The seven role labels a caller can pin to one flagged team within a
// scenario -- purely descriptive/organizational on the backend, but each
// has a natural-language meaning and a sensible default `positions` filter
// this picker pre-fills when it's chosen (see ROLE_DEFAULT_POSITIONS below).
export type ScenarioRole =
  | "high_scoring"
  | "low_scoring"
  | "positive_script"
  | "negative_script"
  | "pass_funnel"
  | "extended_game"
  | "any";

// One flagged team within a scenario, plus the role the caller thinks that
// team is playing this week and, optionally, which of that team's
// positions actually benefit from it -- mirrors the backend's
// LineupScenarioTeamFlag exactly.
export interface LineupScenarioTeamFlag {
  team: string;
  role: ScenarioRole;
  // Empty list means "any position counts".
  positions: string[];
}

// The scenario builder's own local shape before it's sent to the evaluate
// endpoint -- mirrors the backend's LineupScenarioDefinition exactly.
export interface LineupScenarioDefinition {
  label: string;
  team_flags: LineupScenarioTeamFlag[];
}

export interface ScenarioTeamStack {
  team: string;
  // Echoed back from the request's own LineupScenarioTeamFlag.
  role: ScenarioRole;
  positions: string[];
  count: number;
  satisfied: boolean;
}

export interface LineupScenarioMatch {
  label: string;
  satisfied: boolean;
  team_stacks: ScenarioTeamStack[];
}

export interface LineupScenarioResult {
  lineup: UploadedLineup;
  matches: LineupScenarioMatch[];
}

export interface LineupScenarioAnalysis {
  results: LineupScenarioResult[];
  unresolved_player_names: string[];
  min_stack_size: number;
}

// Game Recaps -- walterfootball.com's own per-game recap text, scraped and
// stored verbatim. away_team/home_team are the REAL home/away split,
// resolved from the Schedule file server-side (see backend/schemas/
// game_recap/game_recap.py's own docstring for why the site's own
// score-line text order can't be trusted for this).
export interface GameRecapEntry {
  away_team: string;
  home_team: string;
  away_team_score: number;
  home_team_score: number;
  recap_text: string;
}

export interface GameRecapWeekSnapshot {
  season: number;
  week: number;
  scraped_at: string;
  source_url: string;
  games: GameRecapEntry[];
}

// Response from POST /api/game-recap/scrape -- see backend/api/game_recap/
// scrape.py. `messages` covers any game whose team name(s) didn't resolve
// to this app's abbreviations (still included in the snapshot, just
// flagged here too) or that came back with no recap text at all.
export interface GameRecapScrapeResult {
  snapshot: GameRecapWeekSnapshot;
  messages: string[];
}

// The one game in `snapshot` involving `team` (either side), or null if
// `snapshot` is null (nothing scraped for this season/week yet) or no game
// in it mentions `team` (bye week, or an unresolved/misspelled name).
// Frontend mirror of backend/schemas/game_recap/game_recap.py's own
// find_team_recap -- kept here rather than imported since the frontend has
// no access to the Python module.
export function findTeamRecap(snapshot: GameRecapWeekSnapshot | null, team: string): GameRecapEntry | null {
  if (snapshot === null) return null;
  return snapshot.games.find((g) => g.away_team === team || g.home_team === team) ?? null;
}
