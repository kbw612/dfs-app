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
  "For a week that hasn't been explicitly scored yet, this starts from the opponent's own Team Default Factor at this position (set in Settings' Team Default Factors grid) instead of a flat 2.0 -- editing it here only overrides that one week, the team-wide Default itself is unchanged.",
];

export const OWNERSHIP_NOTES: string[] = [
  "Sub 10% = 3 points",
  "Between 10 and 20% = 2 points",
  "Over 20% = 1 point",
];

// DST's own Ownership breakpoints -- tighter than offense's OWNERSHIP_NOTES
// since DST ownership tends to concentrate on far fewer options each
// week. Same column/refresh icon as offense, just a different rule behind
// it for this position (see backend/services/ownership/scoring.py's
// score_dst_ownership_pct).
export const DST_OWNERSHIP_NOTES: string[] = [
  "2% or under = 3 points",
  "Between 2% and 9.99% = 2 points",
  "10% or higher = 1 point",
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

// DST-only -- there's no separate Ownership/Talent concept for a defense,
// just how attractively priced its salary is this week. Unlike Game
// Environment/Ownership's own suggestions (both computed server-side from
// Vegas Lines/Ownership% data), this rule is a pure function of the DST's
// own salary, already known client-side -- see PlayerPoolView.tsx's own
// suggestedSalaryValue and its header reset (↻) icon for this column.
export const SALARY_VALUE_NOTES: string[] = [
  "Salary $3,500 or higher = 1 point",
  "Salary $2,600 or under = 3 points",
  "Anything in between = 2 points",
  "The reset (↻) icon next to this header resets every DST's value back to this rule -- overwrites whatever's currently saved for each one this week.",
];

// DST-only -- rough weather (rain/wind/snow) tends to suppress the passing
// game and favor defenses/special teams, so a red or orange Weather note on
// a DST's own game is treated as a reason to like that DST more this week.
// See backend/services/weather/scoring.py's score_weather_color -- same
// "refresh icon recomputes and overwrites every row from live data" pattern
// as Ownership's own refresh icon (backend/api/player_pool/
// calculate_weather_scores.py).
export const WEATHER_NOTES: string[] = [
  "Red or orange weather note on this DST's own game = 3 points",
  "Anything else (including no notable weather at all this week) = 2 points",
  "Pulled from the Weather tab's own snapshot for this game -- a game nobody flagged that week just stays at the neutral 2.",
  "The refresh (↻) icon next to this header recomputes every DST's value from the Weather tab's current data -- overwrites whatever's currently saved for each one this week.",
];
