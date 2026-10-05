"""
Computes the Game Logs Against tab's rows -- the inverse of Game Logs
(game_logs_engine.py): instead of a team's own roster's scoring history,
this shows how every OPPOSING player performed in their own game against
a given team, across that team's last `lookback_weeks` games. Mirrors the
person's own prior DKPlayersWeeksScoringAgainst.ipynb workflow exactly
(same "walk this team's own recent schedule, pull whoever they played
each week, list that opponent's real box score" approach) -- ported to
this app's own DK Players tracker + Schedule file instead of a one-off
GitHub CSV pull.

Unlike Game Logs, there's no "currently rostered" snapshot concept here --
the schedule itself (not the tracker) drives which weeks/opponents to
look at, so a since-released/traded player who faced this team earlier in
the season still shows up (their tracker row for that specific week is
what's read, not their team's rows -- see build_game_logs_against_rows).
DST is included and exempt from the zero-FPTS filter, same convention and
same reasoning as Game Logs' own ROSTER_POSITIONS -- see this module's
reuse of that constant.

touches/targets/receptions/receiving_yards/rush_att/rush_yards and
target_share_pct/touch_share_pct/opp_share_pct are read/derived from
`stat_line`, same as Game Logs' own build_game_log_rows -- touches via
usage_shares.compute_touches, the shares from three extra trailing
columns (TGT_SHARE/TOUCH_SHARE/OPP_SHARE) written once per week onto the
FantasyData files by the "Calc Week Points" action (see
backend/services/shared/usage_shares.py), the rest straight off the
file's own columns. None (not 0) for a position whose FantasyData file
doesn't carry that column at all (e.g. QB has no targets/receptions),
same convention as GameLogRow.

`stat_lines_by_position` (optional -- see backend/services/dk_players/
weekly_stats_loader.py's load_weekly_stat_lines) is what both the shares
and QB's own passing line are read from. Left at its default (None -> {})
by every caller that doesn't have the FantasyData files handy -- every
row's shares/passing fields then simply come back None, same as a missing
Schedule file already does for game_location.

`name_aliases` resolves the same cross-source spelling drift Game Logs'
own build_game_log_rows handles (see that module's docstring) -- an
opponent's tracker row and their FantasyData stat line don't always agree
on spelling (e.g. "Brian Robinson Jr." vs. "Brian Robinson"), so the
lookup tries the tracker's own name first, then falls back through
name_aliases via name_lookup_candidates()."""

from __future__ import annotations

from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_logs.game_logs_against import GameLogAgainstRow
from backend.services.game_logs.game_logs_engine import Position, ROSTER_POSITIONS, tier_for_stat_value
from backend.services.game_logs.scoring import multiplier, pct_of_total
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location
from backend.services.shared.name_match import name_lookup_candidates
from backend.services.shared.usage_shares import compute_touches


def build_game_logs_against_rows(
    tracker_rows: list[DkPlayerRow],
    schedule_rows: list[ScheduleRow],
    team: str,
    week: int,
    lookback_weeks: int,
    stat_lines_by_position: dict[Position, dict[tuple[str, int], dict[str, int | float | str]]] | None = None,
    name_aliases: dict[str, str] | None = None,
) -> list[GameLogAgainstRow]:
    """`team`'s own schedule rows in [week - lookback_weeks, week) (i.e.
    the same "strictly before the target week" window Game Logs uses,
    just anchored on `week` directly rather than a tracker-derived
    reference week -- there's no roster snapshot here for `week` itself to
    fall back from) name each week's opponent; for each such week/opponent
    pair, every one of that opponent's tracker rows for that exact week is
    a real "this player's stats from their game against `team`" data
    point. A bye week (or a week the Schedule file has no row for at all)
    simply contributes no opponent to look up, same gap Game Logs' own
    week-skipping shows.

    Sorted most-recent-week-first, matching the person's own script's
    Team/Week-descending sort -- callers that want a different order
    (e.g. by position, then FPTS) resort client-side, same convention as
    Game Logs' own frontend-side grouping.

    The passing fields are looked up from `stat_lines_by_position` by the
    opponent's own (name, week) -- see this module's own docstring for why
    target_share_pct/touch_share_pct, unlike these, come from the tracker
    row instead."""
    stat_lines_by_position = stat_lines_by_position or {}
    name_aliases = name_aliases or {}
    min_week = week - lookback_weeks
    opponent_by_week: dict[int, str] = {
        r.week: r.opponent
        for r in schedule_rows
        if r.team == team and min_week <= r.week < week and r.opponent not in ("BYE", "")
    }

    rows: list[GameLogAgainstRow] = []
    for wk in sorted(opponent_by_week, reverse=True):
        opponent = opponent_by_week[wk]
        for r in tracker_rows:
            if r.team != opponent or r.week != wk or r.position not in ROSTER_POSITIONS:
                continue
            if r.position != "DST" and r.fpts == 0.0:
                continue
            schedule_entry = opponent_and_location(schedule_rows, r.team, r.week)
            game_location = schedule_entry[1] if schedule_entry else None

            position_stat_lines = stat_lines_by_position.get(r.position, {})
            stat_line: dict[str, int | float | str] = {}
            for candidate in name_lookup_candidates(r.name, name_aliases):
                found = position_stat_lines.get((candidate, r.week))
                if found is not None:
                    stat_line = found
                    break
            touches = compute_touches(stat_line)

            rows.append(
                GameLogAgainstRow(
                    against_team=team,
                    week=r.week,
                    name=r.name,
                    position=r.position,
                    salary=r.salary,
                    game_location=game_location,  # type: ignore[arg-type]
                    multiplier=multiplier(r.fpts, r.salary),
                    fpts=r.fpts,
                    non_td_fpts=r.non_td_fpts,
                    non_td_fpts_pct=pct_of_total(r.non_td_fpts, r.fpts),
                    td_fpts=r.td_fpts,
                    td_fpts_pct=pct_of_total(r.td_fpts, r.fpts),
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
    return rows
