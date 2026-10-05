// DFS Type options for Settings' Player Default Factors grid (see
// backend/schemas/player_defaults/player_defaults.py's dfs_types field).
// Rendered as independent checkboxes, not a dropdown -- a player can carry
// any combination of these at once (e.g. both Boom/Bust and Standalone), so
// there's no "None" sentinel here: an empty dfs_types list already means
// "no tag set." Add new categories here as they come up; nothing else needs
// to change on the backend since dfs_types is a plain list of strings
// there, not a constrained enum.
export const DFS_TYPE_OPTIONS = ["Boom/Bust", "Standalone"] as const;

// The one category the Boom/Bust Players tab (BoomBustView.tsx) actually
// filters on today -- centralized here so that tab and this checkbox list
// can't silently drift apart if the display label ever changes.
export const BOOM_BUST_DFS_TYPE = "Boom/Bust";

// Marks a player as fine to roster without anyone else from his own game
// (not his QB, not the opposing QB) -- see PlayerDefaultEntry.dfs_types'
// own docstring. Not enforced anywhere yet; today it's just a tag shown in
// Settings and Player Rankings, saved per-week like Volume/Talent (see
// PlayerPoolEntry.standalone). Future use is a lineup-optimizer validator
// that flags a non-Standalone player rostered without any game-mates.
export const STANDALONE_DFS_TYPE = "Standalone";
