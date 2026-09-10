// Shared by VegasLinesView (where these rules were first defined) and
// OwnershipSummaryView (which colors team names by the same rules) --
// pulled out here so both tabs are guaranteed to agree rather than
// maintaining two copies of the same thresholds that could drift apart.

export type GameEnvironmentTier = "green" | "yellow" | "red";

// Same thresholds as backend/services/game_environment/scoring.py's
// score_game_environment (0/0.5/1 point bands), reimplemented here purely
// for coloring a team's *current* implied total -- these tabs are raw
// browse views of the Vegas Lines scrape, not tied to whether Game
// Environment has actually been applied yet for this game. null (no
// implied total yet) gets no color at all rather than defaulting to a
// tier.
export function gameEnvironmentTier(teamTotal: number | null, overUnder: number | null): GameEnvironmentTier | null {
  if (teamTotal === null) return null;
  if (teamTotal >= 24 || (teamTotal >= 22 && overUnder !== null && overUnder >= 47)) return "green";
  if (teamTotal >= 20) return "yellow";
  return "red";
}

// The O/U line's own tiering -- a separate rule from gameEnvironmentTier
// above (different thresholds, and O/U doesn't need a team total to
// qualify for green the way a team's implied total does): >=47 green,
// 42-46.99 yellow, <42 red. null (no O/U yet) gets no color.
export function overUnderTier(overUnder: number | null): GameEnvironmentTier | null {
  if (overUnder === null) return null;
  if (overUnder >= 47) return "green";
  if (overUnder >= 42) return "yellow";
  return "red";
}

// "vegas-lines-tier-green/yellow/red" (see App.css) -- undefined (no
// class at all) for a null tier, same "no color rather than a default
// tier" convention as the functions above.
export function tierClassName(tier: GameEnvironmentTier | null | undefined): string | undefined {
  return tier ? `vegas-lines-tier-${tier}` : undefined;
}
