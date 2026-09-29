"""
Lineup Scenarios schema -- a person uploads a batch of already-built
lineups (exported from an external optimizer, not this app's own
Optimal Lineup feature) and asks "which of my hand-picked team stacks
does each lineup actually satisfy?" Pure stack-counting against a
lineup's own rostered teams -- no fantasy-point projection math
anywhere in this feature, unlike Contest Results' optimal-lineup
scoring.

Two upload/compute steps, same shape as every other CSV-backed tab in
this app:
  1. POST /api/lineup-scenarios/upload (backend/api/lineup_scenarios/
     upload_csv.py) -- saves the raw lineup CSV text, scoped by
     (season, week, platform, contest) same as the DK salary file.
  2. POST /api/lineup-scenarios/evaluate (backend/api/lineup_scenarios/
     evaluate.py) -- loads that saved CSV plus the week's DK salary
     snapshot (for team resolution by player name -- see
     backend/services/lineup_scenarios/team_resolution.py), and scores
     the caller's own scenario definitions against every lineup.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# The seven role labels a caller can pin to one flagged team within a
# scenario (see LineupScenarioTeamFlag) -- purely descriptive/organizational
# on the backend (this feature does no fantasy-point projection math, so a
# role has no computed effect on matching beyond whatever `positions` filter
# the caller pairs it with), but each has a natural-language meaning and a
# sensible default depth-slot filter the frontend pre-fills when it's
# chosen (depth slots, not bare positions -- see
# UploadedLineupPlayer.depth_slot -- e.g. "RB1"/"RB2", not just "RB"):
#   high_scoring    -- shootout side, hits/exceeds implied total (all skill slots)
#   low_scoring     -- comes in under its implied total (DST/RB1/RB2)
#   positive_script -- winning/leading, favors that team's own run game (RB1/RB2)
#   negative_script -- losing/trailing, favors garbage-time passing (WR/TE slots)
#   pass_funnel     -- heavy passing volume regardless of score (WR/TE slots)
#   extended_game   -- OT/back-and-forth finish inflates volume both ways (all skill slots)
#   any             -- no specific role, just "this team shows up" (no default filter)
#
# A caller can also flag the SAME team more than once within one scenario
# (multiple LineupScenarioTeamFlag entries sharing a `team`) to combine
# roles -- e.g. BUF flagged once as positive_script/["RB1"] and again as
# pass_funnel/["WR1","WR2"] -- both flags are evaluated and counted
# independently (see LineupScenarioMatch.satisfied), so BOTH must clear
# min_stack_size for the scenario to be satisfied, not either/or.
ScenarioRole = Literal[
    "high_scoring",
    "low_scoring",
    "positive_script",
    "negative_script",
    "pass_funnel",
    "extended_game",
    "any",
]


class UploadedLineupPlayer(BaseModel):
    # "QB", "RB", "WR", "TE", "FLEX", "DST", etc. -- taken verbatim from
    # the uploaded CSV's own header row (backend/services/
    # lineup_scenarios/lineup_upload_parser.py), not a fixed enum, since
    # different optimizer exports may order/label roster slots slightly
    # differently. NOT the same thing as `position` below -- a "FLEX" slot
    # could be filled by an RB, WR, or TE, so this alone can't answer "is
    # this player a WR" for a position-filtered scenario team flag.
    roster_position: str
    # Bare player name with the trailing " (12345678)" DraftKings player-ID
    # suffix already stripped -- see lineup_upload_parser.py's docstring
    # for why team resolution has to go by name at all (this app stores no
    # numeric DK player ID anywhere).
    name: str
    # Resolved by matching `name` (case-insensitive, whitespace-normalized)
    # against the current week's DK salary snapshot's own player names --
    # None if no match was found, in which case `name` is also added to
    # LineupScenarioAnalysis.unresolved_player_names so the caller knows
    # this player won't count toward any team's stack count.
    team: str | None
    # This player's own real NFL position (QB/RB/WR/TE/DST), resolved from
    # the same salary-snapshot name match as `team` -- see
    # team_resolution.py. Needed alongside `roster_position` specifically
    # because of the FLEX ambiguity noted above: a scenario team flag's own
    # `positions` filter (LineupScenarioTeamFlag.positions) has to check
    # this field, not roster_position, to correctly count e.g. "just this
    # team's RBs" when that RB happens to be slotted in FLEX. None
    # whenever `team` is also None (unresolved name).
    position: str | None = None
    # This player's own depth-chart slot, e.g. "RB1", "WR2" -- position
    # combined with their 1-indexed rank within that position group on
    # their own team, resolved via backend/services/ownership/depth_rank.py's
    # build_depth_rank_lookup against the latest depth-chart snapshot (see
    # team_resolution.py). This, not the coarser `position` above, is what a
    # scenario team flag's own `positions` filter actually checks -- e.g.
    # ["RB1"] means "just this team's starting RB", not "any RB". DST has no
    # meaningful depth (one defense per team) so it always resolves to the
    # literal string "DST" rather than a ranked slot. None whenever `team`
    # is unresolved, the position isn't depth-tracked, or no depth-chart
    # snapshot has been scraped yet.
    depth_slot: str | None = None


class UploadedLineup(BaseModel):
    # 1-based position in the uploaded file -- stable regardless of any
    # later sort/filter the frontend applies, so "lineup #7" always means
    # the same row.
    index: int
    players: list[UploadedLineupPlayer]


class LineupScenarioTeamFlag(BaseModel):
    """One flagged team within a scenario, plus the role the caller thinks
    that team is playing this week and, optionally, which of that team's
    positions actually benefit from it -- e.g. {team: "BUF", role:
    "positive_script", positions: ["RB"]} for "BUF wins big, so specifically
    count BUF's rostered RBs" rather than any BUF player at all."""

    team: str
    role: ScenarioRole
    # Empty list means "any position counts" (this feature's original,
    # simpler behavior) -- a non-empty list restricts stack-counting to
    # just those specific depth-chart slots (see
    # UploadedLineupPlayer.depth_slot), e.g. ["RB1"] or ["WR1", "WR2"], NOT
    # bare positions -- "RB" alone never matches anything since resolved
    # players carry a depth-qualified slot like "RB1"/"RB2", not "RB". The
    # frontend pre-fills this from the chosen role's own default (see
    # ScenarioRole's own docstring above) but the caller can edit it freely
    # before adding the scenario.
    positions: list[str] = []


class LineupScenarioDefinition(BaseModel):
    # Free-text description the caller made up for this scenario, e.g.
    # "BUF/KC shootout" -- purely for display, never used for matching.
    label: str
    # Every flagged team that must each independently clear min_stack_size
    # (counting only players matching that flag's own `positions` filter,
    # if any) for this scenario to be satisfied -- e.g. two flags for "both
    # teams go off", or a single flag for "just the away team in this
    # game." Replaces this feature's original flat `teams: list[str]`
    # (still readable as a degenerate case: role="any", positions=[]).
    team_flags: list[LineupScenarioTeamFlag]


class ScenarioTeamStack(BaseModel):
    team: str
    # Echoed back from the request's own LineupScenarioTeamFlag so the
    # frontend's hover breakdown can show what was actually being checked
    # (e.g. "BUF (positive_script, RB): 2") without holding a separate copy
    # of the scenario definition it already sent.
    role: ScenarioRole
    positions: list[str] = []
    # How many of this lineup's 9 rostered players resolved to `team` AND
    # (positions is empty or that player's own resolved position is in
    # positions) -- see lineup_scenario_engine.py's _matching_player_count.
    count: int
    # count >= the evaluate endpoint's min_stack_size -- broken out
    # per-team (rather than just being implied by the parent match's own
    # `satisfied`) so the frontend can show a per-team breakdown on hover
    # even when the overall scenario fails because only one of several
    # teams cleared the bar.
    satisfied: bool


class LineupScenarioMatch(BaseModel):
    label: str
    # True only if every team in this scenario's own definition cleared
    # min_stack_size -- i.e. every entry in team_stacks has satisfied=True.
    # A scenario with an empty team_flags list is vacuously satisfied
    # (nothing to fail), though the frontend's scenario builder shouldn't
    # produce one -- see lineup_scenario_engine.py's evaluate_scenario.
    satisfied: bool
    team_stacks: list[ScenarioTeamStack]


class LineupScenarioResult(BaseModel):
    lineup: UploadedLineup
    # One entry per scenario passed to POST /evaluate, same order as the
    # request -- so the frontend can render one results column per
    # scenario without re-sorting.
    matches: list[LineupScenarioMatch]


class LineupScenarioAnalysis(BaseModel):
    results: list[LineupScenarioResult]
    # Every uploaded-lineup player name that didn't match any player in
    # the salary snapshot, deduped -- "partial feature still useful"
    # convention (same as DK Players' possible_stat_name_mismatches):
    # the whole request never fails just because a few names didn't
    # resolve, it just surfaces them so the caller knows those players
    # can't count toward any team's stack.
    unresolved_player_names: list[str]
    # Echoed back from the request so the frontend's results table can
    # label what threshold produced these satisfied/unsatisfied calls
    # without holding onto its own separate copy of the value it sent.
    min_stack_size: int
