"""
Game Preview (Phase A) -- one entry per this week's actual game (from the
Schedule file, same "AWAY @ HOME" grouping Game Logs/Multipliers/DST Trends
already use), carrying the team-level context a Game Preview tab needs
before any player-level Play/Fade/Monitor tagging is layered on top (that's
Phase B, not built yet -- see the plan discussed for this feature).

Every side-channel input here degrades gracefully when its own data hasn't
been scraped/uploaded yet for this (season, week) -- same "missing optional
data means None, not an error" convention as every other tab that reads
Vegas Lines/Weather/Team Default Factors. Only a missing Schedule file (no
games to even list) is a hard failure at the API layer -- see
backend/api/game_preview/game_preview.py's own docstring.

Unlike Multipliers/DST Trends (which always review `week - 1`, the last
*completed* week), this tab's own Vegas/Weather/Team Factors context is for
`week` itself -- the upcoming game being previewed, not a past one. Only the
DST/Off Trends matchup piece looks backward (through `week - 1`, over a
trailing window), since that's a team's recent form feeding into how this
week's matchup might play out -- see GamePreviewDstMatchup's own docstring.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.game_logs.game_logs import TeamStatSummaryRow


class GamePreviewVegas(BaseModel):
    # All three None when the Vegas Lines scrape has no row for this game
    # yet, or the scraped team names didn't resolve (see VegasLineGame's
    # own docstring) -- same graceful-degradation convention as everywhere
    # else. Values are always the `current` snapshot (most recent scrape),
    # not `initial` -- a preview tab wants the latest line, not the
    # start-of-week baseline Vegas Lines' own tab tracks drift against.
    over_under: float | None = None
    away_implied_total: float | None = None
    home_implied_total: float | None = None
    # Verbatim scraped kickoff line, display only -- None under the same
    # conditions as the three fields above.
    kickoff_label: str | None = None


class GamePreviewWeather(BaseModel):
    # None (the whole GamePreviewGame.weather field, not just this) when
    # this game has no notable-weather note this week -- see WeatherGame's
    # own docstring: only games the meteorologist actually flagged appear
    # in the Weather scrape at all, so "no note" is the common case, not a
    # missing-data problem.
    color: str
    note: str


# One entry per roster position DST-relevant Team Default Factors already
# cover (QB/RB/WR/TE/DST) -- None for any position that's never been
# explicitly set in the Settings grid (see TeamFactorEntry.factor's own
# docstring), same "unset means None" convention, not a pre-populated 2.0.
# This represents the TEAM's OWN factor -- i.e. how tough (low) or exploitable
# (high) that team's defense is against an OPPONENT player at that position,
# per Team Default Factors' own docstring -- so a GamePreviewTeamSide's own
# `team_factors` describes what THIS team's defense does to the OTHER side's
# players at each position, not this team's own offensive players.
class GamePreviewTeamFactors(BaseModel):
    qb: float | None = None
    rb: float | None = None
    wr: float | None = None
    te: float | None = None
    dst: float | None = None


# This team's own recent DST-trend numbers (forcing) alongside the
# opponent's own recent numbers as an offense (allowing) -- e.g. this team's
# DST has forced 4.2 sacks/game over the trailing window, and the opponent's
# offense has allowed 4.5 sacks/game in that same window, suggesting a
# favorable pass-rush matchup this week. None when there's no trailing
# window to review yet (week 1 of the season -- see build_dst_trend_
# leaderboards' own "through_week < 1" case) or this team/opponent has no
# DST stat lines in that window (bye-heavy early season, or the DST weekly
# stats file hasn't been scraped at all).
class GamePreviewDstMatchup(BaseModel):
    games: int
    sacks_per_game_forced: float
    takeaways_per_game_forced: float
    opponent_sacks_per_game_allowed: float
    opponent_takeaways_per_game_allowed: float


# One played week's worth of this team's own offensive pace, used as an
# entry in GamePreviewPaceTrend.trailing -- same four pace numbers as the
# parent object's own single-week snapshot, plus that week's own opponent
# and its own week-over-week deltas (vs. the played week immediately before
# THIS one, not necessarily the trend object's own top-level "most recent
# week" comparison) so a weeks-as-columns table can show the shift at every
# column, not just the newest one.
class GamePreviewPaceWeek(BaseModel):
    week: int
    # This team's own opponent that week, from the Schedule file -- "BYE"
    # is never possible here since a bye week never has a stat line to
    # build a GamePreviewPaceWeek from in the first place. None only when
    # no Schedule file covers that week/team at all (schedule_rows == [],
    # or a row genuinely missing for that combination).
    opponent: str | None = None
    # "home" or "away" -- this team's own side of that week's game, from
    # the Schedule file's own GameLocation column, so a caller can render
    # "vs DEN" (home) vs. "@ DEN" (away) instead of a location-blind "vs".
    # None under the exact same condition as `opponent` (no Schedule
    # coverage for that team/week).
    opponent_location: Literal["home", "away"] | None = None
    plays: int
    pass_att: int
    rush_att: int
    pass_rate_pct: float | None = None
    rush_rate_pct: float | None = None
    # vs. the played week immediately before THIS one (not the trend
    # object's own top-level "most recent" comparison) -- None for the
    # oldest week in `trailing` when there's no earlier played week at all
    # to diff against (this team's very first played week of the season).
    plays_delta: int | None = None
    pass_rate_delta: float | None = None
    # Always pass_rate_delta's negation (100 - pass_rate_pct is rush's own
    # share, so a shift toward pass is an equal shift away from rush) --
    # stored as its own field rather than left for the frontend to negate,
    # same "always store both rates" convention as pass_rate_pct/
    # rush_rate_pct above.
    rush_rate_delta: float | None = None


# This team's own offensive pace for the most recently PLAYED week before
# the game being previewed (skips bye weeks -- `week` is that real week,
# not necessarily `preview_week - 1`), plus how that compares to the week
# before it. See game_preview_matchups.py's build_team_pace_trend for the
# exact computation (reuses the same team_usage_totals() aggregate Game
# Logs' own share fields are built from). None (the whole
# GamePreviewTeamSide.pace_trend field, not just this) when this team has
# no played week with any FantasyData stat line at all yet (week 1, or no
# weekly stats files uploaded).
class GamePreviewPaceTrend(BaseModel):
    week: int
    plays: int
    pass_att: int
    rush_att: int
    pass_rate_pct: float | None = None
    # Always pass_rate_pct's complement (100 - pass_rate_pct), stored as its
    # own field rather than left for callers to derive, since the narrative
    # now always states both rates side by side (see
    # game_preview_narrative.py's own _pace_line) -- None under the exact
    # same condition as pass_rate_pct (no plays that week).
    rush_rate_pct: float | None = None
    # vs. the week before `week` -- None when there's no such prior played
    # week to compare against (this team's very first played week of the
    # season, or a bye-week gap right before it).
    plays_delta: int | None = None
    pass_rate_delta: float | None = None
    # Up to `window_weeks` most recently PLAYED weeks strictly before the
    # game being previewed, ordered NEWEST FIRST (trailing[0] duplicates
    # this same object's own week/plays/pass_att/etc as its first entry --
    # kept as a real entry rather than skipped, so a caller rendering a
    # weeks-as-columns table doesn't need to special-case "the first column
    # is somewhere else"). Fewer than window_weeks entries whenever this
    # team doesn't have that many played weeks yet (early season, or bye
    # weeks in the window) -- never padded with placeholder weeks. Empty
    # list under the exact same "no data at all" condition that makes the
    # whole GamePreviewPaceTrend field None.
    trailing: list[GamePreviewPaceWeek] = []


# One offensive position this team's own DEFENSE has been a soft/
# exploitable matchup for over the trailing window -- see
# game_preview_matchups.py's build_positional_matchup_signals for the exact
# two-part rule (above-average FPTS allowed AND multiple high-multiplier
# games allowed, both required). Appears on the DEFENSE's own
# GamePreviewTeamSide.exploitable_positions (i.e. "this team's own defense
# is exploitable at these positions"), not the opponent's -- the opponent's
# players at this position are the ones that get tagged/narrated as a
# result (see build_team_player_tags' own opponent_exploitable_positions
# param and game_preview_narrative.py's own Matchup Trends section).
class GamePreviewPositionalMatchup(BaseModel):
    position: str
    games: int
    avg_fpts_allowed: float
    league_avg_fpts: float
    high_multiplier_games: int


# Phase B -- one player-level signal that fired, with a plain-English
# reason (see backend/services/game_preview/game_preview_player_tags.py for
# every rule that can produce one of these). A player can carry multiple
# tags at once (e.g. both a Breakout Watch "play" and a low-ownership
# "leverage" tag) -- these are independent rule checks, not a single
# forced verdict.
class GamePreviewPlayerTag(BaseModel):
    kind: Literal["play", "fade", "monitor", "leverage", "chalk"]
    reason: str


# Only players with at least one fired tag appear in GamePreviewTeamSide's
# own `players` list -- a player with no signal isn't noise worth showing,
# same "no signal, no row" convention as Breakout Watch/Repeat Performers
# only listing qualifying players.
class GamePreviewPlayer(BaseModel):
    name: str
    position: str
    team: str
    # 1-indexed depth-chart rank within `position` (e.g. 1 for a starting
    # WR1, 4 for a WR4) -- same convention as InjuryPlayerEntry.depth. None
    # when no depth-chart snapshot was supplied to build_game_preview at
    # all (Phase-A/B-era callers/tests), or this player's name doesn't
    # match anyone on that snapshot's own roster for this team.
    depth: int | None = None
    tags: list[GamePreviewPlayerTag] = Field(default_factory=list)


# Phase D -- one player-level row inside an injury group (see
# game_preview_injuries.py's own module docstring for the four groups a
# player can land in). `starred` mirrors Star Players' own flag -- the
# frontend renders it as a gold star next to the name (same convention as
# Depth Charts/Injury Report), NOT as a separate group of its own (that
# separate "Star Players" group existed in an earlier version of this
# feature and was folded into this per-entry flag instead, per explicit
# feedback that a star deserves an icon next to their name in whichever
# group they already qualify for, not a whole extra bullet).
class GamePreviewInjuryEntry(BaseModel):
    player: str
    position: str
    depth: int
    status: str
    starred: bool = False


# One group's worth of injury entries (e.g. every Offensive Line player at
# depth 1 who has a status this week) -- `label` is the display heading
# ("O-Line (depth 1)", etc.). Only groups with >=1 entry appear in
# GamePreviewTeamSide.injury_groups at all -- see that field's own
# docstring for the "no signal, no row" convention this follows.
class GamePreviewInjuryGroup(BaseModel):
    label: str
    entries: list[GamePreviewInjuryEntry] = Field(default_factory=list)


class GamePreviewTeamSide(BaseModel):
    team: str
    is_home: bool
    team_factors: GamePreviewTeamFactors
    dst_matchup: GamePreviewDstMatchup | None = None
    # This team's own recent offensive pace -- see GamePreviewPaceTrend's
    # own docstring. None under the same "no played week yet" conditions
    # described there.
    pace_trend: GamePreviewPaceTrend | None = None
    # Which offensive positions THIS team's own defense has been a soft
    # matchup for -- see GamePreviewPositionalMatchup's own docstring for
    # why this lives on the defense's own side rather than the opponent's.
    # Empty when nothing clears both of that signal's own thresholds (the
    # common case), same "no signal, no row" convention as everywhere else
    # in this feature.
    exploitable_positions: list[GamePreviewPositionalMatchup] = Field(default_factory=list)
    # Sum of ownership_pct across this team's own rostered QB/RB/WR/TE rows
    # (DST excluded) -- same "combined ownership% across every rostered
    # player on the team (DST excluded)" rule the Ownership Summary tab's
    # own computeTeamOwnership() uses (frontend/src/components/
    # OwnershipSummaryView.tsx), reused here so "this team's total
    # projected ownership" means the same thing on both tabs. None when
    # there's no ownership data at all for this team (Ownership hasn't been
    # scraped/uploaded this week, or this team has zero matching rows) --
    # distinct from 0.0, which would misleadingly claim a real computed
    # total. See game_preview_matchups.py's team_projected_ownership_pct.
    projected_ownership_pct: float | None = None
    # Empty when Phase B's inputs (DK Players tracker, usage shares,
    # Ownership, Usage Bump Players) haven't been supplied to
    # build_game_preview at all -- same graceful-degradation convention as
    # every optional field above, so Phase A callers/tests keep working
    # unchanged (see build_game_preview's own keyword defaults).
    players: list[GamePreviewPlayer] = Field(default_factory=list)
    # Phase D -- this team's OWN injury summary, one group per position
    # bucket (see backend/services/game_preview/game_preview_injuries.py's
    # own module docstring for the exact groups and their rules): O-Line/
    # Defensive Front/Defensive Backs (each depth 1 only), and offensive
    # skill positions (QB/RB/WR/TE, depth 1-4) -- a starred player shows a
    # gold star on their own entry (see GamePreviewInjuryEntry.starred)
    # rather than getting a separate group. Empty when no depth-chart
    # snapshot was supplied at all, or this team is fully healthy in every
    # group -- same "no signal, no row" convention as everywhere else in
    # this feature.
    injury_groups: list[GamePreviewInjuryGroup] = Field(default_factory=list)
    # This team's own Rush Att/Rush Yds/Rush TD/Pass Att/Pass Yds/Pass TD/
    # Rec TD average+median over the trailing `window_weeks` -- the exact
    # same TeamStatSummaryRow/StatAverage shape (and the same
    # average_tier/median_tier red/green volume thresholds) Game Logs'
    # own "Team Summary (Avg / Median)" section already computes (see
    # backend/services/game_logs/game_logs_engine.py's
    # build_team_stat_summary/tier_for_stat_value) -- reused directly
    # rather than re-derived, so "above/below threshold" means the same
    # thing on both tabs. None when this team has no played week with any
    # stat line in the window at all (same "no data yet" condition as
    # pace_trend being None).
    stat_summary: TeamStatSummaryRow | None = None
    # Two INDEPENDENT tiers, not a single mutually-exclusive pick -- a
    # team can be "high" on run volume AND "low" on pass volume (or any
    # other combination) at once. Derived purely from `stat_summary`'s own
    # average_tier values (see game_preview_engine.py's
    # _volume_tier_flags): run_volume_tier is "high" when Rush Att or Rush
    # Yds tiers "high" (checked first), else "low" when either tiers
    # "low", else None (both sit strictly between their own thresholds);
    # pass_volume_tier mirrors this for Pass Att/Pass Yds. Both None
    # together can mean either "no data at all" (`stat_summary` itself is
    # None) or "this team's volume is genuinely in the normal range on
    # both sides" (`stat_summary` exists, neither stat tripped a
    # threshold) -- callers that need to tell those two apart should check
    # `stat_summary` directly rather than inferring it from these two
    # fields (see frontend TeamStatSummaryColumn's own usage).
    run_volume_tier: Literal["low", "high"] | None = None
    pass_volume_tier: Literal["low", "high"] | None = None


# Phase C -- one section of the auto-generated summary (see
# game_preview_narrative.py's own module docstring). `label` is None for
# the standalone Vegas line (displayed as a single bullet with no heading
# of its own) and set for every other section ("O vs D Line Matchup",
# "Pace", "Matchup Trends", "Ownership", "Plays to consider", "Fade",
# "Monitor") -- the frontend renders a labeled section as a heading
# followed by its own nested bullet list, and a None-labeled section as a
# single flat bullet.
class GamePreviewNarrativeSection(BaseModel):
    label: str | None = None
    entries: list[str] = Field(default_factory=list)


class GamePreviewGame(BaseModel):
    # Same "-".join(sorted(...)) convention as every other Game filter's
    # own key (see backend/services/shared/game_matchup.py's game_key).
    key: str
    # "AWAY @ HOME", same convention/helper as Game Logs/Multipliers/DST
    # Trends' own game grouping.
    label: str
    teams: list[str]
    vegas: GamePreviewVegas | None = None
    weather: GamePreviewWeather | None = None
    away: GamePreviewTeamSide
    home: GamePreviewTeamSide
    # Phase C -- a handful of deterministic, rule-based sections combining
    # this game's own Vegas/DST-matchup context with its two sides' player
    # tags (see backend/services/game_preview/game_preview_narrative.py's
    # own module docstring for why these are fixed string templates, not
    # free-form/model-generated prose, same "fully rule-based" decision as
    # every Phase B tag). Weather is deliberately NOT one of these sections
    # -- see that module's docstring for why it's rendered as its own
    # dedicated line by the frontend instead, off `weather` above. Always
    # non-empty -- a game with nothing notable in any category still gets
    # one real fallback section rather than an empty list (see
    # build_game_narrative's own docstring).
    narrative_sections: list[GamePreviewNarrativeSection] = Field(default_factory=list)
    # away.projected_ownership_pct + home.projected_ownership_pct -- None
    # when NEITHER side has any ownership data this week (see
    # GamePreviewTeamSide.projected_ownership_pct's own docstring); a side
    # missing data while the other has some still sums (treating the
    # missing side as 0), same convention the Ownership Summary tab's own
    # per-player sum uses for a player missing ownership_pct.
    combined_projected_ownership_pct: float | None = None
    # combined_projected_ownership_pct / vegas.over_under -- "how much
    # combined ownership this game's own Vegas total is buying," expressed
    # as ownership percentage points per O/U point. A LOWER ratio means a
    # comparable scoring environment (per the O/U) is available at a lower
    # combined roster-ownership cost -- see game_preview_matchups.py's
    # total_to_ownership_ratio for the exact rule. None when either
    # combined_projected_ownership_pct or vegas.over_under is unavailable
    # (or over_under is 0).
    total_to_ownership_ratio: float | None = None
    # vegas.over_under >= HIGH_OVER_UNDER_PCT (47.0 -- see
    # game_preview_matchups.py) -- surfaced as its own flag (rather than
    # making the frontend re-derive it from vegas.over_under) so the
    # Ownership narrative section's own ratio bullet can be highlighted for
    # a high-total game without the frontend re-implementing the threshold.
    # Always False when vegas or vegas.over_under is None.
    high_over_under: bool = False
    # vegas.over_under <= LOW_OVER_UNDER_PCT (40.0 -- see
    # game_preview_matchups.py) -- the low-total mirror of high_over_under
    # above, same reasoning. Always False when vegas or vegas.over_under is
    # None (never both True/False confused -- 40 and 47 don't overlap).
    low_over_under: bool = False


class GamePreviewResult(BaseModel):
    season: int
    week: int
    # `week - 1` -- the last completed week the DST/Off Trends matchup
    # piece reviews (see GamePreviewDstMatchup's own docstring). Kept at
    # the result level (not just buried inside each game) so the frontend
    # can show "DST trends through week N" once, same as DST Trends' own
    # through_week field.
    through_week: int
    window_weeks: int
    games: list[GamePreviewGame] = Field(default_factory=list)
