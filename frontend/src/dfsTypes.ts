// DFS Type options for Settings' Player Default Factors grid (see
// backend/schemas/player_defaults/player_defaults.py's dfs_type field).
// "None" is a UI-only sentinel for the dropdown -- selecting it saves
// dfs_type as null, not the literal string "None" (see SettingsView.tsx's
// inputValueToDfsType). Add new categories here as they come up; nothing
// else needs to change on the backend since dfs_type is a plain string
// there, not a constrained enum.
export const DFS_TYPE_OPTIONS = ["None", "Boom/Bust"] as const;

// The one category the Boom/Bust Players tab (BoomBustView.tsx) actually
// filters on today -- centralized here so that tab and this dropdown list
// can't silently drift apart if the display label ever changes.
export const BOOM_BUST_DFS_TYPE = "Boom/Bust";
