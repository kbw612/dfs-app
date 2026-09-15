"""
Computes the Game Logs tab's rows -- for every player currently rostered
at QB/RB/WR/TE (from the DK Players tracker's most recent snapshot week),
their own FPTS/Non_TD_FPTS/TD_FPTS history for up to `lookback_weeks`
prior weeks, enriched with that week's Opponent/GameLocation (from the
Schedule file, backend/repositories/schedule/schedule_repo.py) and usage
stats (Touches/Targets/Receptions/Receiving Yards/Rush Att/Rush Yards,
from the season's FantasyData weekly stats files -- see
backend/services/dk_players/weekly_stats_loader.py's
load_weekly_stat_lines).

Mirrors the person's own prior workflow of checking a team's recent game
logs before setting a week's DFS lineup. "Currently rostered" means
whatever the DK Players tracker's own snapshot for the *reference week*
says (see build_game_log_rows) -- not every player who's ever had a stat
line at this position for this team, which would include players long
since traded/released/benched.

DST is rostered and shown like every other position, but never checked
against the zero-FPTS filter below -- see build_game_log_rows' own
docstring for why. It still gets no usage-stat enrichment (Touch/Targets/
etc. always come back None) since no FantasyData file exists for
defenses -- POSITIONS below (QB/RB/WR/TE only) is what the API layer
still uses to decide which 4 stat files to load; DST was never a key into
that dict and still isn't. TD_FPTS/Non_TD_FPTS still have no meaningful
split for defense scoring either (see calculate_week_points, which never
computes a TD component for DST) -- a DST's whole FPTS just shows up as
Non_TD_FPTS, same as it always has everywhere else in this app.
"""

from __future__ import annotations

from typing import Literal

from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_logs.game_logs import GameLogRow, GameOption
from backend.services.game_logs.scoring import multiplier as _multiplier
from backend.services.game_logs.scoring import pct_of_total as _pct
from backend.services.schedule.schedule_loader import ScheduleRow, games_for_week, opponent_and_location
from backend.services.shared.game_matchup import game_label as _format_game_label
from backend.services.shared.game_matchup import resolve_away_home

Position = Literal["QB", "RB", "WR", "TE"]

POSITIONS: tuple[Position, ...] = ("QB", "RB", "WR", "TE")

# Who's eligible to be "currently rostered"/shown at all -- POSITIONS
# above plus DST (included per an explicit request to show DSTs
# regardless of score). Not itself a `Position` (DST has no FantasyData
# stat file), so kept as its own plain-str tuple rather than widening the
# Position Literal everywhere else in this module. Public (not
# underscore-prefixed) since game_logs_against_engine.py's own roster
# concept -- "every opposing player who faced this team" -- uses the same
# QB/RB/WR/TE/DST set.
ROSTER_POSITIONS: tuple[str, ...] = (*POSITIONS, "DST")


def build_game_options(schedule_rows: list[ScheduleRow], week: int) -> list[GameOption]:
    """This week's games from the Schedule file, ordered by label for a
    stable display order -- one option per matchup, skipping bye weeks
    (nothing to pick as an opponent). Empty if the Schedule file hasn't
    been uploaded yet (schedule_rows == []).

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
    stat_lines_by_position: dict[Position, dict[tuple[str, int], dict[str, int]]],
    week: int,
    lookback_weeks: int,
) -> tuple[list[GameLogRow], int]:
    """Returns (rows, reference_week).

    reference_week is the latest tracker week <= `week` -- used to decide
    "who's currently rostered" (see this module's docstring); it's `week`
    itself once that week's "Add Week Players" has run, otherwise the
    latest earlier week that has rows, so this tab still works before
    that action for the current week. (0, []) -- reference_week 0 -- if
    the tracker has no rows at all for season/platform yet.

    Each such player's own rows cover every week from
    reference_week - lookback_weeks through reference_week - 1 for which
    the tracker actually has a row for them (bye weeks, or weeks before
    the player was added/rostered, simply have no row and are skipped --
    same gap the person's own spreadsheet shows), MINUS any week where
    they scored exactly 0 FPTS -- a zero week is almost always "didn't
    play" rather than a meaningful data point, and it clutters the table
    for the deep bench/committee players this tab surfaces the most. DST
    is the one exception: its own row shows regardless of score, since a
    defense's FPTS (even 0) is itself a real signal, not just noise from
    an inactive/unused player."""
    candidate_weeks = [r.week for r in tracker_rows if r.week <= week]
    if not candidate_weeks:
        return [], 0
    reference_week = max(candidate_weeks)
    min_week = reference_week - lookback_weeks

    rows_by_name_position: dict[tuple[str, str], list[DkPlayerRow]] = {}
    for r in tracker_rows:
        rows_by_name_position.setdefault((r.name, r.position), []).append(r)

    roster = {
        (r.name, r.position, r.team)
        for r in tracker_rows
        if r.week == reference_week and r.position in ROSTER_POSITIONS
    }

    rows: list[GameLogRow] = []
    for name, position, _current_team in roster:
        for r in rows_by_name_position.get((name, position), []):
            if not (min_week <= r.week < reference_week):
                continue
            if position != "DST" and r.fpts == 0.0:
                continue
            schedule_entry = opponent_and_location(schedule_rows, r.team, r.week)
            opponent = schedule_entry[0] if schedule_entry else None
            game_location = schedule_entry[1] if schedule_entry else None
            stat_line = stat_lines_by_position.get(position, {}).get((name, r.week), {})
            touches = None
            if "rush_att" in stat_line:
                touches = stat_line.get("rush_att", 0) + stat_line.get("receptions", 0)
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
                    rush_att=stat_line.get("rush_att"),
                    rush_yards=stat_line.get("rush_yards"),
                )
            )
    return rows, reference_week
