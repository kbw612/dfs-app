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
