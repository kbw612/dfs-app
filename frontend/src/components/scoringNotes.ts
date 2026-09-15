// Shared scoring-rule text for the Game Environment, Matchup, Ownership, Volume/
// Opportunities, and Talent/Explosiveness column headers -- shown via
// HeaderInfoPopover in both PlayerPoolView.tsx and SettingsView.tsx's
// Player Default Factors grid, so the same columns explain themselves
// identically everywhere they appear.
export const GAME_ENVIRONMENT_NOTES: string[] = [
  "3 points: team total ~24+, or 22+ with a game over/under of 47 or more",
  "2 points: team total 20-23.75",
  "1 point: team total 19 or less",
  "The expected game flow, pace, and scoring -- think over/unders for sports betting (a guide, not an absolute).",
  "A general starting point: over/unders of 49+, OR players on teams with implied totals of 25+.",
  "Probably the most important factor each week -- how a game will likely play out (or how it might play out differently than the consensus) is easy to overlook.",
];

export const GAME_MATCHUP_NOTES: string[] = [
  "How an offense as a whole, a specific part of the offense (run game or pass game), or an individual player (e.g. a WR/CB matchup) lines up against the defense across from them -- both a micro (player-level) and macro (team offense vs. defense) read.",
  "Does the WR have a tough draw against a top-end CB?",
  "Does the RB face a defense with a fierce front seven?",
  "Is the defense a high-end unit that's been holding opponents to low yardage and scoring totals?",
  "Scored once per team and position, not per player -- editing one player's value applies it to every teammate at that same position (e.g. all of a team's WRs share one Matchup score).",
];

export const OWNERSHIP_NOTES: string[] = [
  "Sub 10% = 3 points",
  "Between 10 and 20% = 2 points",
  "Over 20% = 1 point",
];

export const VOLUME_OPPORTUNITIES_NOTES: string[] = [
  "3 of 3 = 1 point",
  "2 of 3 = .5 points",
  "0-1 of 3 = 0 points",
  "Team's primary ball carrier (will see over 60% of the RB carries)",
  "Goal Line usage",
  "Team's lead receiving back/regularly used in the passing game",
];

export const TALENT_EXPLOSIVENESS_NOTES: string[] = [
  "top player = 1 point",
  "above player = .5 points",
  "average player = 0 points",
];
