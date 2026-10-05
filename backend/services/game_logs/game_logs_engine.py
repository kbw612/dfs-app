"""
Computes the Game Logs tab's rows -- for every player currently rostered
at QB/RB/WR/TE/DST (from the DK Players tracker's most recent snapshot
week), their own FPTS/Non_TD_FPTS/TD_FPTS history for up to
`lookback_weeks` prior weeks, enriched with that week's Opponent/
GameLocation (from the Schedule file, backend/repositories/schedule/
schedule_repo.py) and usage stats (Touches/Targets/Receptions/Receiving
Yards/Rush Att/Rush Yards, -- QB only -- their own Cmp/Att/Cmp%/Yds/Avg/
TD/Int/Sck/Rtg passing line, and -- DST only -- their own sacks recorded),
all read live from the season's FantasyData weekly stats files -- see
backend/services/dk_players/weekly_stats_loader.py's
load_weekly_stat_lines.

TGTSHARE/TOUCHSHARE/OPPSHARE are read straight off `stat_line`, same as
every other usage stat here -- they're three extra trailing columns
(TGT_SHARE/TOUCH_SHARE/OPP_SHARE) this app writes onto the FantasyData
files themselves, once per week, as part of the "Calc Week Points" action (see
backend/services/shared/usage_shares.py and backend/api/dk_players/
calculate_week.py) rather than being recomputed live in this module. A
file that predates one of those columns (or a week "Calc Week Points"
hasn't run for yet) simply has no matching key in its stat line, same
"not applicable yet" convention as every other optional column below.

`stat_lines_by_position` is keyed by the FantasyData file's own spelling
of a player's name, which doesn't always match the DK Players tracker's
spelling (e.g. tracker "Brian Robinson Jr." vs. stat file "Brian
Robinson") -- the same cross-source suffix-drift problem
backend/services/shared/name_match.py exists for. build_game_log_rows
resolves this the same way dk_players_engine.py's calculate_week_points
does: try the tracker's own name first (most rows agree natively), then
fall back through `name_aliases` (Settings' Name Aliases panel) via
name_lookup_candidates(). Without a matching alias entry, a genuine
spelling mismatch just looks like "no stats recorded" (every usage field
comes back None) -- same as any other missing stat line.

Mirrors the person's own prior workflow of checking a team's recent game
logs before setting a week's DFS lineup. "Currently rostered" means
whatever the DK Players tracker's own snapshot for the *reference week*
says (see build_game_log_rows) -- not every player who's ever had a stat
line at this position for this team, which would include players long
since traded/released/benched.

DST is rostered and shown like every other position, but never checked
against the zero-FPTS filter below -- see build_game_log_rows' own
docstring for why. It now gets real usage-stat enrichment too (a `sacks`
field, from FantasyData_DSTs.csv's own DEF_SCK column) now that a
FantasyData file exists for defenses -- POSITIONS below (now including
DST) is what the API layer uses to decide which stat files to load.
TD_FPTS/Non_TD_FPTS now have a real split for DST too (DEF_TD/RET_TD via
calculate_week_points), same as every other position.
"""

from __future__ import annotations

from statistics import median as _median
from typing import Callable, Literal, Protocol, TypeVar

from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_logs.game_logs import GameLogRow, GameOption, StatAverage, TeamStatSummaryRow
from backend.services.game_logs.scoring import multiplier as _multiplier
from backend.services.game_logs.scoring import pct_of_total as _pct
from backend.services.schedule.schedule_loader import ScheduleRow, games_for_week, opponent_and_location
from backend.services.shared.game_matchup import game_label as _format_game_label
from backend.services.shared.game_matchup import resolve_away_home
from backend.services.shared.name_match import name_lookup_candidates
from backend.services.shared.usage_shares import compute_touches

Position = Literal["QB", "RB", "WR", "TE", "DST"]

POSITIONS: tuple[Position, ...] = ("QB", "RB", "WR", "TE", "DST")

# Who's eligible to be "currently rostered"/shown at all -- same set as
# POSITIONS now that DST has its own FantasyData file too. Kept as its own
# name (rather than just using POSITIONS directly everywhere) since it
# predates DST joining POSITIONS and game_logs_against_engine.py's own
# roster concept -- "every opposing player who faced this team" -- imports
# this one specifically, not POSITIONS.
ROSTER_POSITIONS: tuple[str, ...] = POSITIONS


def build_game_options(
    schedule_rows: list[ScheduleRow], week: int, contest_teams: set[str] | None = None
) -> list[GameOption]:
    """This week's games from the Schedule file, ordered by label for a
    stable display order -- one option per matchup, skipping bye weeks
    (nothing to pick as an opponent). Empty if the Schedule file hasn't
    been uploaded yet (schedule_rows == []).

    `contest_teams` (optional) narrows the full Schedule-file slate down to
    just the games actually on the currently-selected Contest's own slate
    -- e.g. a single-window "Classic Main" contest only ever salaries a
    subset of the week's real NFL games, so the Schedule file (which has
    every game league-wide, same "All Games" scope the DK Players tracker
    itself always reads) would otherwise show games the person can't
    actually roster from. `contest_teams` is the set of teams appearing in
    that contest's own DK salary file (see backend/api/game_logs/
    game_logs.py) -- a game is kept only if BOTH its teams are in that
    set, since a game with just one side on the slate would mean a data
    mismatch, not a real playable matchup. Left at its default (None) skips
    this filter entirely, same "nothing to narrow by yet" convention as
    every other optional/None param here -- e.g. no salary file uploaded
    for the current contest yet just means every league-wide game still
    shows, rather than the whole tab going blank.

    Each label is "AWAY @ HOME" (see backend/services/shared/
    game_matchup.py), not an alphabetical "vs" -- either team's own
    schedule row names its own real home/away side for this week (that
    team's GameLocation column), so one of the two teams (whichever sorts
    first) is used to look that up via opponent_and_location(); both
    teams' own rows always agree on which side is home, so it doesn't
    matter which one is picked. Falls back to an alphabetical "vs" label
    only if the schedule data is unexpectedly missing a row for that team/
    week (shouldn't happen -- games_for_week already sourced this matchup
    from the same schedule_rows -- but this keeps the tab usable rather
    than raising on a malformed file)."""
    options = []
    for teams_set in games_for_week(schedule_rows, week):
        if contest_teams is not None and not teams_set <= contest_teams:
            continue
        teams = sorted(teams_set)
        schedule_entry = opponent_and_location(schedule_rows, teams[0], week)
        resolved = (
            resolve_away_home(teams[0], schedule_entry[0], schedule_entry[1] == "Home")
            if schedule_entry is not None
            else None
        )
        label = _format_game_label(*resolved) if resolved is not None else " vs ".join(teams)
        options.append(GameOption(key="-".join(teams), label=label, teams=teams))
    options.sort(key=lambda o: o.label)
    return options


def build_game_log_rows(
    tracker_rows: list[DkPlayerRow],
    schedule_rows: list[ScheduleRow],
    stat_lines_by_position: dict[Position, dict[tuple[str, int], dict[str, int | float | str]]],
    week: int,
    lookback_weeks: int,
    name_aliases: dict[str, str] | None = None,
    contest_teams: set[str] | None = None,
) -> tuple[list[GameLogRow], int]:
    """Returns (rows, reference_week).

    `contest_teams` (optional) restricts the "currently rostered" set to
    just the teams on the currently-selected Contest's own DK salary slate
    -- same reasoning and same source (that contest's salary file's own
    teams) as build_game_options' own `contest_teams` param above. A player
    whose team isn't on that slate this week simply doesn't show, same as
    every other roster-narrowing filter in this app. None (the default)
    keeps every league-wide rostered player, unchanged from before this
    param existed.

    reference_week is the latest tracker week <= `week` -- used ONLY to
    decide "who's currently rostered" (see this module's docstring); it's
    `week` itself once that week's "Add Week Players" has run, otherwise
    the latest earlier week that has rows, so the roster this tab shows
    is never blank before that action for the current week. (0, []) --
    reference_week 0 -- if the tracker has no rows at all for
    season/platform yet.

    The history WINDOW, by contrast, is anchored on the raw requested
    `week`, not reference_week -- every week from week - lookback_weeks
    through week - 1 that the tracker has a row for a given rostered
    player, same as game_logs_against_engine.py's own raw-week window.
    This deliberately decouples "how far back history goes" from
    "whether this week's own roster snapshot has been added yet": once
    it's week 2, week 1's own complete game data should show up as
    history immediately, even if "Add Week 2 Players" (which is what
    would normally advance reference_week to 2) hasn't run yet -- there's
    no reason viewing LAST week's results should depend on THIS week's
    salary file being uploaded. (Once reference_week does reach `week`,
    the two bounds coincide and behave exactly as before.)

    Each such player's own rows cover that window for which the tracker
    actually has a row for them (bye weeks, or weeks before the player
    was added/rostered, simply have no row and are skipped -- same gap
    the person's own spreadsheet shows), MINUS any week where they scored
    exactly 0 FPTS -- a zero week is almost always "didn't play" rather
    than a meaningful data point, and it clutters the table for the deep
    bench/committee players this tab surfaces the most. DST is the one
    exception: its own row shows regardless of score, since a defense's
    FPTS (even 0) is itself a real signal, not just noise from an
    inactive/unused player."""
    name_aliases = name_aliases or {}
    candidate_weeks = [r.week for r in tracker_rows if r.week <= week]
    if not candidate_weeks:
        return [], 0
    reference_week = max(candidate_weeks)
    min_week = week - lookback_weeks

    rows_by_name_position: dict[tuple[str, str], list[DkPlayerRow]] = {}
    for r in tracker_rows:
        rows_by_name_position.setdefault((r.name, r.position), []).append(r)

    roster = {
        (r.name, r.position, r.team)
        for r in tracker_rows
        if r.week == reference_week
        and r.position in ROSTER_POSITIONS
        and (contest_teams is None or r.team in contest_teams)
    }

    rows: list[GameLogRow] = []
    for name, position, _current_team in roster:
        for r in rows_by_name_position.get((name, position), []):
            if not (min_week <= r.week < week):
                continue
            if position != "DST" and r.fpts == 0.0:
                continue
            schedule_entry = opponent_and_location(schedule_rows, r.team, r.week)
            opponent = schedule_entry[0] if schedule_entry else None
            game_location = schedule_entry[1] if schedule_entry else None
            position_stat_lines = stat_lines_by_position.get(position, {})
            stat_line: dict[str, int | float | str] = {}
            for candidate in name_lookup_candidates(name, name_aliases):
                found = position_stat_lines.get((candidate, r.week))
                if found is not None:
                    stat_line = found
                    break
            touches = compute_touches(stat_line)

            rows.append(
                GameLogRow(
                    week=r.week,
                    name=name,
                    position=position,
                    team=r.team,
                    salary=r.salary,
                    opponent=opponent,
                    game_location=game_location,  # type: ignore[arg-type]
                    multiplier=_multiplier(r.fpts, r.salary),
                    fpts=r.fpts,
                    non_td_fpts=r.non_td_fpts,
                    non_td_fpts_pct=_pct(r.non_td_fpts, r.fpts),
                    td_fpts=r.td_fpts,
                    td_fpts_pct=_pct(r.td_fpts, r.fpts),
                    touches=touches,
                    targets=stat_line.get("targets"),
                    receptions=stat_line.get("receptions"),
                    receiving_yards=stat_line.get("receiving_yards"),
                    rec_td=stat_line.get("rec_td"),
                    rush_att=stat_line.get("rush_att"),
                    rush_yards=stat_line.get("rush_yards"),
                    rush_td=stat_line.get("rush_td"),
                    target_share_pct=stat_line.get("target_share_pct"),
                    touch_share_pct=stat_line.get("touch_share_pct"),
                    opp_share_pct=stat_line.get("opp_share_pct"),
                    pass_cmp=stat_line.get("pass_cmp"),
                    pass_att=stat_line.get("pass_att"),
                    pass_cmp_pct=stat_line.get("pass_cmp_pct"),
                    pass_yds=stat_line.get("pass_yds"),
                    pass_avg=stat_line.get("pass_avg"),
                    pass_td=stat_line.get("pass_td"),
                    pass_int=stat_line.get("pass_int"),
                    pass_sck=stat_line.get("pass_sck"),
                    pass_rtg=stat_line.get("pass_rtg"),
                    pass_att_tier=tier_for_stat_value("pass_att", stat_line.get("pass_att")),
                    pass_yds_tier=tier_for_stat_value("pass_yds", stat_line.get("pass_yds")),
                    sacks=stat_line.get("sacks"),
                )
            )
    return rows, reference_week


# Background-color thresholds for the 4 passing/rushing volume stats that
# get red/green shading, in both the Team Stat Summary (StatAverage's own
# average_tier/median_tier, applied to the averaged/medianed team-week
# totals) and the per-week grid (GameLogRow/GameLogAgainstRow's own
# pass_att_tier/pass_yds_tier, applied to a single week's raw value --
# deliberately NOT extended to rush_att/rush_yards there, since the
# person's own request only colors the passing columns per-week; rush/rec
# already have their own unrelated top-2-share shading computed client-
# side). Each tuple is (red-threshold, green-threshold): at or under the
# first is "low" (red), at or over the second is "high" (green), anything
# in between is None (no shading) -- see tier_for_stat_value.
_STAT_TIER_THRESHOLDS: dict[str, tuple[float, float]] = {
    "pass_yds": (175, 261),
    "pass_att": (28, 38),
    "rush_yards": (85, 141),
    "rush_att": (21, 30),
}


def tier_for_stat_value(field: str, value: float | int | None) -> Literal["low", "high"] | None:
    """The single shared source of truth for every "color this stat's
    background" decision this feature makes -- both StatAverage's
    average_tier/median_tier (game_logs.py) and GameLogRow/
    GameLogAgainstRow's own pass_att_tier/pass_yds_tier call this with the
    same `field` name and thresholds, so a week's raw value and this same
    stat's team-week average/median are always judged by identical rules.
    None for a `value` of None, for a `field` with no entry in
    _STAT_TIER_THRESHOLDS (Rec TD, Rush TD, Pass TD -- no thresholds
    requested for these), or for a value that falls strictly between the
    two thresholds (no shading)."""
    if value is None:
        return None
    thresholds = _STAT_TIER_THRESHOLDS.get(field)
    if thresholds is None:
        return None
    low, high = thresholds
    if value <= low:
        return "low"
    if value >= high:
        return "high"
    return None


# The 7 counting stats TeamStatSummaryRow summarizes -- see that schema's
# own docstring (Receptions/Receiving Yards were dropped at the person's
# own request). Order here is what build_team_stat_summary iterates in;
# doesn't affect the response shape (each is its own named field), just
# kept in the same Rush/Pass block order the main Game Logs grid itself
# uses for these columns.
_SUMMARY_STAT_FIELDS: tuple[str, ...] = (
    "rec_td",
    "rush_att",
    "rush_yards",
    "rush_td",
    "pass_att",
    "pass_yds",
    "pass_td",
)


class _StatSummaryRow(Protocol):
    """Structural type for whatever row build_team_stat_summary is called
    with (GameLogRow or GameLogAgainstRow) -- both already carry identical
    field names/types for every field referenced here, so one function
    serves both tabs (see each engine's own call site for how `get_team`
    differs)."""

    week: int
    rec_td: int | None
    rush_att: int | None
    rush_yards: int | None
    rush_td: int | None
    pass_att: int | None
    pass_yds: int | None
    pass_td: int | None


_RowT = TypeVar("_RowT", bound=_StatSummaryRow)


def _average_and_median(field: str, values: list[float]) -> StatAverage:
    """None/None/None/None when `values` is empty -- i.e. every one of
    this team's own weeks had this particular stat's team total as None
    (not a real 0), same "not applicable" convention StatAverage's own
    docstring describes. `field` decides average_tier/median_tier via
    tier_for_stat_value -- None for both on a stat with no thresholds
    (Rec TD, Rush TD, Pass TD)."""
    if not values:
        return StatAverage(average=None, median=None, average_tier=None, median_tier=None)
    average = sum(values) / len(values)
    median = float(_median(values))
    return StatAverage(
        average=average,
        median=median,
        average_tier=tier_for_stat_value(field, average),
        median_tier=tier_for_stat_value(field, median),
    )


def build_team_stat_summary(rows: list[_RowT], get_team: Callable[[_RowT], str]) -> list[TeamStatSummaryRow]:
    """A TEAM-level summary, not a per-player one: for each team, for each
    week that team has at least one row, every one of that team's own rows
    for that week is summed per stat into a single team-week total (a
    None-valued field -- e.g. Pass Yds on a non-QB row -- contributes
    nothing to the sum, same "not applicable" exclusion as everywhere else
    in this app; a week where NO row for that team has a non-None value
    for a stat leaves that week out of the stat's own average/median
    entirely, rather than counting it as 0). Each of the 7
    _SUMMARY_STAT_FIELDS is then averaged/medianed across however many of
    that team's own weeks had a real team total for it (see
    _average_and_median).

    `team` comes from `get_team`, since GameLogRow's own roster team and
    GameLogAgainstRow's own `against_team` panel grouping are different
    fields on the two row types. `rows` is expected to already be
    whatever's actually being shown (post zero-FPTS filtering, within the
    lookback window) -- this function does no week-window filtering of its
    own, so the summary always matches what's on screen, per the person's
    own "only the weeks shown" answer.

    `games` on each result row is the count of that team's own distinct
    weeks with at least one row (not the count behind any one stat's own
    average, which can be fewer -- e.g. a bye-week-free team with no QB
    row one week still counts that week in `games`, just not in Pass Yds'
    own average).

    Sorted by team -- a stable, predictable order the frontend can render
    directly without re-sorting (consistent with this module's "no calcs
    on the frontend" design for this feature)."""
    rows_by_team_week: dict[tuple[str, int], list[_RowT]] = {}
    for row in rows:
        key = (get_team(row), row.week)
        rows_by_team_week.setdefault(key, []).append(row)

    # Per-team: for each of its own weeks, one team-total value per stat
    # (or no entry at all for a stat that week if nothing contributed).
    team_week_totals: dict[str, dict[str, list[float]]] = {}
    team_games: dict[str, int] = {}
    for (team, _week), week_rows in rows_by_team_week.items():
        team_games[team] = team_games.get(team, 0) + 1
        stat_totals = team_week_totals.setdefault(team, {field: [] for field in _SUMMARY_STAT_FIELDS})
        for field in _SUMMARY_STAT_FIELDS:
            values = [getattr(row, field) for row in week_rows if getattr(row, field) is not None]
            if values:
                stat_totals[field].append(float(sum(values)))

    summaries: list[TeamStatSummaryRow] = []
    for team in sorted(team_week_totals):
        stat_totals = team_week_totals[team]
        summaries.append(
            TeamStatSummaryRow(
                team=team,
                games=team_games[team],
                **{field: _average_and_median(field, stat_totals[field]) for field in _SUMMARY_STAT_FIELDS},
            )
        )
    return summaries
