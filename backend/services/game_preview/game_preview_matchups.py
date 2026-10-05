"""
Game Preview -- team-level trend signals that move INTO this tab rather
than living on Game Logs/Game Logs Against (see the "unwind the Game Logs
Trends work, rebuild it here instead" course-correction this feature took):

1. build_team_pace_trend -- this team's own recent offensive pace (total
   plays, pass rate) and how it's shifted week-over-week, plus a
   `window_weeks`-sized trailing history of the same numbers for a
   weeks-as-columns table view (see GamePreviewPaceTrend.trailing).
   Genuinely new to Game Preview (the other two trend features the person
   asked to move here -- player share-trend deltas and Breakout Watch --
   already existed on this tab via game_preview_player_tags.py's own
   _share_trend_tags/_multiplier_tags, so only this one needed building).

2. build_positional_matchup_signals -- the NEW signal from this course-
   correction, per Kevin's own framing: "if a team has been giving up FPTS
   or high multipliers to certain positions, that's a signal to consider
   players in that position [on the other team]." Combines both parts (his
   own "Both" answer) -- a team only counts as a soft matchup for a
   position when it's allowing ABOVE-AVERAGE FPTS to that position AND has
   allowed multiple high-multiplier games to it, over the same trailing
   window. Either alone is noise: a single shootout inflates FPTS without
   being a real trend, and a single spike-multiplier game happens to every
   defense occasionally.

3. team_projected_ownership_pct/combined_projected_ownership_pct/
   total_to_ownership_ratio/is_high_over_under -- a "game environment
   leverage" angle: how much combined roster ownership a game's own Vegas
   total is buying. A game with a similarly high O/U but much lower combined
   ownership than another offers a comparable scoring environment at a
   fraction of the roster density (i.e. it's easier to be uniquely exposed
   to that game's ceiling). See each function's own docstring.

All three reuse existing data/helpers rather than re-deriving them: pace
trend reuses team_usage_totals() (the same aggregate Game Logs' own share
fields are built from); the positional-matchup signal reuses the DK Players
tracker + Schedule file (the same two inputs Game Logs Against's own
build_game_logs_against_rows walks), just aggregated across every team's
opponents in one pass instead of one team at a time (there's no single
"opponent" here -- every team is somebody's opponent at once); the
ownership functions reuse the same OwnershipPlayer list/ownership_pct field
already threaded into build_game_preview for Phase B's own leverage/chalk
tags (see game_preview_player_tags.py's own _ownership_tag).
"""

from __future__ import annotations

import statistics
from typing import Literal

from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_preview.game_preview import GamePreviewPaceTrend, GamePreviewPaceWeek, GamePreviewPositionalMatchup
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.game_logs.scoring import multiplier as _multiplier
from backend.services.ownership.ownership_totals import sum_current_ownership_pct
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location
from backend.services.shared.usage_shares import team_usage_totals

# "High" O/U games, per an explicit "high O/U games are 47 or more" rule --
# used to flag a game's own Ownership narrative bullet (see
# game_preview_narrative.py) and GamePreviewGame.high_over_under, so a
# genuinely big Vegas total gets called out regardless of how its ratio
# happens to land.
HIGH_OVER_UNDER_PCT = 47.0

# "Low" O/U games, per an explicit "40 and under O/U" rule -- the mirror of
# HIGH_OVER_UNDER_PCT above, used the same way (GamePreviewGame.low_over_under
# and the Ownership narrative bullet's own low-total note). Inclusive (<=) so
# a game sitting exactly at 40 reads as low; still no overlap with
# HIGH_OVER_UNDER_PCT since the two thresholds sit 7 points apart (40 to 47).
LOW_OVER_UNDER_PCT = 40.0

# Offensive positions this signal considers -- DST is excluded (a "team has
# allowed high FPTS to opposing DSTs" framing doesn't map to a DFS "consider
# this position" call the way it does for QB/RB/WR/TE).
_OFFENSE_POSITIONS = ("QB", "RB", "WR", "TE")

# -- Positional matchup signal thresholds --
# A defense needs at least this many real GAMES (not player-rows -- see
# build_positional_matchup_signals' own docstring on why that distinction
# matters) against a position in the window before its own average is
# trusted at all (1 game is one data point, not a trend).
MIN_GAMES_FOR_SIGNAL = 2
# "Above average" means at least this ratio over the position's own
# league-wide average FPTS-allowed-per-game in the same window (15% over,
# not just any positive delta -- a defense that's 2% over average isn't a
# real signal).
ABOVE_AVERAGE_FPTS_RATIO = 1.15
# A second, independent floor on top of the ratio above: the ratio alone
# lets a low-value position (say a league where RBs average only 3-4
# FPTS/game allowed) flag a defense that's "above average" while still
# being useless for lineup construction. Per-game combined FPTS allowed to
# the position must also clear this absolute bar, in addition to beating
# the league average -- these are rough DK-scoring "worth playing" floors,
# not derived from any formula.
MIN_AVG_FPTS_ALLOWED_BY_POSITION: dict[str, float] = {"QB": 18.0, "RB": 14.0, "WR": 14.0, "TE": 10.0}
# Same Multiplier scale Repeat Performer/Breakout Watch already use
# elsewhere in this app (see game_preview_player_tags.py's own constants) --
# 3.5x is one tier below Repeat Performer's own 4.0x "price has caught up"
# bar, since this is about the DEFENSE allowing it, not the player's own
# price tag. Checked against the game's own TOP individual multiplier (see
# below), not a per-game average multiplier -- one player's spike game is
# what "high-multiplier" describes, not the position's combined output.
HIGH_MULTIPLIER_THRESHOLD = 3.5
MIN_HIGH_MULTIPLIER_GAMES = 2


def _plays_and_rates(entry: dict[str, int]) -> tuple[int, float | None, float | None]:
    """(plays, pass_rate_pct, rush_rate_pct) from one team_usage_totals()
    (team, week) aggregate -- the shared arithmetic behind every pace number
    in this module, so the single-week snapshot, its deltas, and every
    trailing entry all compute rates identically."""
    plays = entry["pass_att"] + entry["rush_att"]
    pass_rate_pct = round(entry["pass_att"] / plays * 100, 1) if plays > 0 else None
    rush_rate_pct = round(100 - pass_rate_pct, 1) if pass_rate_pct is not None else None
    return plays, pass_rate_pct, rush_rate_pct


def _pace_week(
    team: str,
    week: int,
    totals: dict[tuple[str, int], dict[str, int]],
    weeks_with_data: list[int],
    schedule_rows: list[ScheduleRow],
) -> GamePreviewPaceWeek:
    """One GamePreviewPaceWeek entry -- this team's own pace for `week`,
    its opponent that week (from the Schedule file), and its own deltas
    against the played week immediately before `week` (found in
    `weeks_with_data`, NOT necessarily the trend object's own top-level
    "most recent" comparison -- see GamePreviewPaceWeek's own docstring).
    Shares its plays/rate arithmetic with the single-week snapshot via
    _plays_and_rates so the two never compute pass/rush rate slightly
    differently."""
    plays, pass_rate_pct, rush_rate_pct = _plays_and_rates(totals[(team, week)])
    schedule_entry = opponent_and_location(schedule_rows, team, week)
    opponent = schedule_entry[0] if schedule_entry is not None else None
    opponent_location: Literal["home", "away"] | None = None
    if schedule_entry is not None and schedule_entry[1] in ("Home", "Away"):
        opponent_location = "home" if schedule_entry[1] == "Home" else "away"

    plays_delta: int | None = None
    pass_rate_delta: float | None = None
    rush_rate_delta: float | None = None
    prior_weeks = [w for w in weeks_with_data if w < week]
    if prior_weeks:
        prior_plays, prior_pass_rate_pct, prior_rush_rate_pct = _plays_and_rates(totals[(team, prior_weeks[-1])])
        plays_delta = plays - prior_plays
        if pass_rate_pct is not None and prior_pass_rate_pct is not None:
            pass_rate_delta = round(pass_rate_pct - prior_pass_rate_pct, 1)
        if rush_rate_pct is not None and prior_rush_rate_pct is not None:
            rush_rate_delta = round(rush_rate_pct - prior_rush_rate_pct, 1)

    return GamePreviewPaceWeek(
        week=week,
        opponent=opponent,
        opponent_location=opponent_location,
        plays=plays,
        pass_att=totals[(team, week)]["pass_att"],
        rush_att=totals[(team, week)]["rush_att"],
        pass_rate_pct=pass_rate_pct,
        rush_rate_pct=rush_rate_pct,
        plays_delta=plays_delta,
        pass_rate_delta=pass_rate_delta,
        rush_rate_delta=rush_rate_delta,
    )


def build_team_pace_trend(
    team: str,
    week: int,
    window_weeks: int,
    stat_lines_by_position: dict[str, dict[tuple[str, int], dict[str, int | float | str]]],
    schedule_rows: list[ScheduleRow],
) -> GamePreviewPaceTrend | None:
    """This team's own total plays/pass rate for the most recently PLAYED
    week strictly before `week` (skips bye weeks and weeks with no
    FantasyData stat lines at all -- the search just looks at whichever
    weeks `team_usage_totals` actually has an entry for), plus the same
    numbers for the played week before THAT one, if any, PLUS up to
    `window_weeks` played weeks' worth of the same numbers (each with its
    own opponent and its own week-over-week deltas) in `trailing` (newest
    first, capped by however many played weeks actually exist -- see
    GamePreviewPaceTrend.trailing's own docstring) for a caller that wants
    to render a multi-week table rather than just the latest snapshot. None
    when this team has no played week at all yet (week 1 of the season, or
    no weekly stats files ever uploaded)."""
    totals = team_usage_totals(stat_lines_by_position)
    weeks_with_data = sorted(w for (t, w) in totals if t == team and w < week)
    if not weeks_with_data:
        return None

    recent_week = weeks_with_data[-1]
    plays, pass_rate_pct, rush_rate_pct = _plays_and_rates(totals[(team, recent_week)])

    plays_delta: int | None = None
    pass_rate_delta: float | None = None
    prior_weeks = [w for w in weeks_with_data if w < recent_week]
    if prior_weeks:
        prior_plays, prior_pass_rate_pct, _prior_rush_rate_pct = _plays_and_rates(totals[(team, prior_weeks[-1])])
        plays_delta = plays - prior_plays
        if pass_rate_pct is not None and prior_pass_rate_pct is not None:
            pass_rate_delta = round(pass_rate_pct - prior_pass_rate_pct, 1)

    trailing_weeks = list(reversed(weeks_with_data[-window_weeks:]))
    trailing = [_pace_week(team, w, totals, weeks_with_data, schedule_rows) for w in trailing_weeks]

    return GamePreviewPaceTrend(
        week=recent_week,
        plays=plays,
        pass_att=totals[(team, recent_week)]["pass_att"],
        rush_att=totals[(team, recent_week)]["rush_att"],
        pass_rate_pct=pass_rate_pct,
        rush_rate_pct=rush_rate_pct,
        plays_delta=plays_delta,
        pass_rate_delta=pass_rate_delta,
        trailing=trailing,
    )


def build_positional_matchup_signals(
    tracker_rows: list[DkPlayerRow],
    schedule_rows: list[ScheduleRow],
    week: int,
    window_weeks: int,
) -> dict[str, list[GamePreviewPositionalMatchup]]:
    """{defense's own team -> its own list of soft-matchup positions},
    computed over every offensive tracker row in [week - window_weeks,
    week). For each such row, its own opponent that week (via the Schedule
    file) is the defense that "allowed" that box score.

    First aggregated by (defense, position, WEEK) -- every player at that
    position who faced that defense that week is combined into one game's
    worth of production (FPTS summed, so a defense that gave up 18 to the
    starting RB and 6 to the backup reads as "24 allowed that game," not two
    separate low-value data points) and one game's own high-water multiplier
    (the single highest individual multiplier that week, since "allowed a
    high-multiplier game" describes one player's spike performance, not a
    combined-output figure). `games` on the final signal is then a count of
    real GAMES (distinct weeks), not player-rows -- averaging by player-row
    instead would understate a defense's real per-game vulnerability (a
    committee backfield's own low-volume backup drags a per-player average
    down even when the position as a whole torched that defense) and would
    also make `games` read as a much bigger, misleading number than the
    defense's own actual game count.

    A defense/position pair only makes the cut when ALL of this module's
    own thresholds clear (see MIN_GAMES_FOR_SIGNAL/ABOVE_AVERAGE_FPTS_RATIO/
    MIN_AVG_FPTS_ALLOWED_BY_POSITION/HIGH_MULTIPLIER_THRESHOLD/
    MIN_HIGH_MULTIPLIER_GAMES above) -- most defense/position pairs won't
    qualify, same "no signal, no row" convention as every other Phase B rule
    in this feature. A team missing entirely from the returned dict (rather
    than present with an empty list) means it had nothing that cleared the
    bar at any position."""
    min_week = week - window_weeks
    # (defense, position, week) -> (combined fpts that game, top individual
    # multiplier that game).
    game_totals: dict[tuple[str, str, int], list[float]] = {}
    game_top_multiplier: dict[tuple[str, str, int], float] = {}

    for row in tracker_rows:
        if row.position not in _OFFENSE_POSITIONS or not (min_week <= row.week < week):
            continue
        schedule_entry = opponent_and_location(schedule_rows, row.team, row.week)
        if schedule_entry is None:
            continue
        opponent = schedule_entry[0]
        if not opponent or opponent == "BYE":
            continue
        key = (opponent, row.position, row.week)
        game_totals.setdefault(key, []).append(row.fpts)
        mult = _multiplier(row.fpts, row.salary)
        if mult is not None:
            game_top_multiplier[key] = max(mult, game_top_multiplier.get(key, 0.0))

    # Collapse to one entry per (defense, position, week): combined FPTS
    # allowed that game, plus whether that game's own top multiplier was
    # "high."
    games_by_defense_position: dict[tuple[str, str], list[tuple[float, bool]]] = {}
    league_game_fpts_by_position: dict[str, list[float]] = {}
    for (team, position, week_num), fpts_values in game_totals.items():
        combined_fpts = sum(fpts_values)
        is_high_multiplier_game = game_top_multiplier.get((team, position, week_num), 0.0) >= HIGH_MULTIPLIER_THRESHOLD
        games_by_defense_position.setdefault((team, position), []).append((combined_fpts, is_high_multiplier_game))
        league_game_fpts_by_position.setdefault(position, []).append(combined_fpts)

    league_avg_by_position = {
        position: sum(values) / len(values) for position, values in league_game_fpts_by_position.items() if values
    }

    signals: dict[str, list[GamePreviewPositionalMatchup]] = {}
    for (team, position), games in games_by_defense_position.items():
        game_count = len(games)
        if game_count < MIN_GAMES_FOR_SIGNAL:
            continue
        league_avg = league_avg_by_position.get(position)
        if not league_avg or league_avg <= 0:
            continue
        avg_fpts_allowed = sum(fpts for fpts, _ in games) / game_count
        min_absolute_fpts = MIN_AVG_FPTS_ALLOWED_BY_POSITION.get(position, 0.0)
        if avg_fpts_allowed < max(league_avg * ABOVE_AVERAGE_FPTS_RATIO, min_absolute_fpts):
            continue
        high_multiplier_games = sum(1 for _, is_high in games if is_high)
        if high_multiplier_games < MIN_HIGH_MULTIPLIER_GAMES:
            continue
        signals.setdefault(team, []).append(
            GamePreviewPositionalMatchup(
                position=position,
                games=game_count,
                avg_fpts_allowed=round(avg_fpts_allowed, 1),
                league_avg_fpts=round(league_avg, 1),
                high_multiplier_games=high_multiplier_games,
            )
        )

    for team_signals in signals.values():
        team_signals.sort(key=lambda s: s.position)
    return signals


def team_projected_ownership_pct(team: str, ownership_players: list[OwnershipPlayer]) -> float | None:
    """Sum of ownership_pct across this team's own rostered QB/RB/WR/TE rows
    (DST excluded) -- delegates to backend/services/ownership/
    ownership_totals.py's sum_current_ownership_pct(), the single shared
    implementation also used by the Ownership Summary tab's own per-team/
    per-game rollups (backend/services/ownership/ownership_summary.py), so
    "this team's total projected ownership" means exactly the same thing on
    both tabs rather than being two independently hand-copied calculations.
    None (not 0.0) when this team has zero matching rows at all -- see that
    function's own docstring."""
    return sum_current_ownership_pct(team, ownership_players)


def combined_projected_ownership_pct(away_pct: float | None, home_pct: float | None) -> float | None:
    """away_pct + home_pct, treating a missing side as 0 -- None only when
    BOTH sides are None (no ownership data for this game at all)."""
    if away_pct is None and home_pct is None:
        return None
    return (away_pct or 0.0) + (home_pct or 0.0)


def total_to_ownership_ratio(combined_pct: float | None, over_under: float | None) -> float | None:
    """combined_pct / over_under -- ownership percentage points "bought" per
    O/U point. Lower means a comparable scoring environment is available at
    a lower combined roster-ownership cost (the leverage angle from this
    feature's own framing: a 49.5 O/U game at 35% combined ownership is a
    much cheaper way to be exposed to a big scoring environment than a 51.5
    O/U game at 110% combined ownership). None when either input is missing
    or `over_under` is 0 (avoids a division by zero for a same-numbers-both-
    sides Vegas placeholder, which shouldn't happen in practice but isn't
    this function's job to validate)."""
    if combined_pct is None or over_under is None or over_under <= 0:
        return None
    return round(combined_pct / over_under, 2)


def is_high_over_under(over_under: float | None) -> bool:
    """True when `over_under` clears HIGH_OVER_UNDER_PCT (47.0, per an
    explicit "high O/U games are 47 or more" rule) -- False (not None) when
    `over_under` itself is None, so callers can use this directly as a
    schema field default without an extra None-check."""
    return over_under is not None and over_under >= HIGH_OVER_UNDER_PCT


def is_low_over_under(over_under: float | None) -> bool:
    """True when `over_under` is at or under LOW_OVER_UNDER_PCT (40.0, per
    an explicit "40 and under O/U" rule) -- False (not None) when
    `over_under` itself is None, same convention as is_high_over_under."""
    return over_under is not None and over_under <= LOW_OVER_UNDER_PCT


# Below this many values, a 33rd/67th percentile split isn't meaningful (and
# statistics.quantiles itself can raise on too-small inputs) -- e.g. week 1
# with only a couple games loaded so far, or a single-game slate. Below this
# count, compute_ownership_bands returns None and nothing gets flagged
# Low/High Own for that week rather than a percentile computed over a
# handful of values reading as more meaningful than it is.
MIN_BAND_SAMPLE_SIZE = 4


def compute_ownership_bands(values: list[float]) -> tuple[float, float] | None:
    """Returns (low_cutoff, high_cutoff) as THIS set's own 33rd/67th
    percentile (inclusive terciles -- top/bottom third) -- used to flag both
    individual teams' and whole games' projected ownership as relatively
    Low/High Own for *this week's own slate*, rather than a fixed absolute
    percentage. What counts as "low owned" shifts slate to slate (a chalky
    week raises the bar for everyone), so ranking against this week's own
    other teams/games is more meaningful than a fixed cutoff -- same
    relative-ranking angle for both the per-team call (pass every team's
    projected_ownership_pct across the week) and the whole-game call (pass
    every game's own combined_projected_ownership_pct), just against a
    different population each time. None when fewer than
    MIN_BAND_SAMPLE_SIZE values are available."""
    if len(values) < MIN_BAND_SAMPLE_SIZE:
        return None
    t1, t2 = statistics.quantiles(values, n=3, method="inclusive")
    return t1, t2


def classify_by_bands(value: float | None, bands: tuple[float, float] | None) -> str | None:
    """"low" when `value` is at or below this set's own bottom-third cutoff,
    "high" when at or above the top-third cutoff, None otherwise --
    including when `value` or `bands` itself is missing (see
    compute_ownership_bands' own docstring for when that happens). Shared by
    both the per-team and whole-game Ownership badges."""
    if value is None or bands is None:
        return None
    low_cutoff, high_cutoff = bands
    if value <= low_cutoff:
        return "low"
    if value >= high_cutoff:
        return "high"
    return None
