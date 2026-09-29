"""
Shared helpers for turning FantasyData weekly stat lines (backend/services/
dk_players/weekly_stats_loader.py's load_weekly_stat_lines -- one dict per
position, keyed by (player name, week), each stat line carrying its own
"team" plus whichever usage columns that position's file has) into TGTSHARE/
TOUCHSHARE/OPPSHARE.

compute_usage_share_updates is the actual entry point -- called once, from
backend/api/dk_players/calculate_week.py's "Calc Week Points" endpoint
(the same action that already reads all 4 position files to compute
TD_FPTS), right after that week's FantasyData files are confirmed present.
Its output is written back onto those same files as TGT_SHARE/TOUCH_SHARE/
OPP_SHARE trailing columns (see backend/repositories/dk_players/weekly_stats_repo.py's
write_usage_share_columns) -- "calc once" here, so every consumer
(game_logs_engine.build_game_log_rows, game_logs_against_engine.
build_game_logs_against_rows, ...) just reads target_share_pct/
touch_share_pct/opp_share_pct straight off the stat line it already has
(same as any other usage stat), rather than recomputing a team-wide
aggregate itself.

The three metrics, each a percentage rounded to 1 decimal:
- TGTSHARE = player's targets / team's combined pass attempts that week
  (the team's QB(s) own PASSING_ATT, not a sum of recorded targets --
  deliberately not the same denominator as the other two).
- TOUCHSHARE = (player carries + player receptions) / (team carries + team
  receptions).
- OPPSHARE = (player carries + player targets) / (team carries + team
  targets) -- a QB has no targets stat at all, so their own OPPSHARE
  numerator/denominator both just treat that side as 0, same "missing
  category treated as 0" precedent as TOUCHSHARE already uses for a QB's
  missing receptions.

team_usage_totals is the one place any of this aggregates ACROSS players
rather than reading a single player's own line -- a share is meaningless
without first knowing the player's team's own combined total for that
week, which requires seeing every position's stat lines, not just
whichever one a given call happens to be about. compute_touches is also
used directly by game_logs_engine for the live Touches display column --
that's a single-player fact with no team-wide aggregate step, so it's
computed on the fly rather than waiting on "Calc Week Points."
"""

from __future__ import annotations


def team_usage_totals(
    stat_lines_by_position: dict[str, dict[tuple[str, int], dict[str, int | float | str]]],
) -> dict[tuple[str, int], dict[str, int]]:
    """{(team, week): {"targets": int, "rush_att": int, "receptions": int,
    "pass_att": int}} -- summed across every stat line in
    `stat_lines_by_position`, across all positions present, so a team's own
    weekly total reflects every WR/RB/TE/QB who recorded a line that week,
    not just whichever ones happen to already be in a given caller's own
    rostered/opponent subset. Kept as four separate sums (rather than one
    combined "touches") since TOUCHSHARE and OPPSHARE need different pairs
    of them and TGTSHARE needs "pass_att" (the team's own QB(s) attempts)
    instead of "targets" entirely. "pass_att" is 0 for any stat line that
    isn't a QB's own (no "pass_att" key at all there), so it naturally only
    picks up QB rows without any position-based branching here."""
    totals: dict[tuple[str, int], dict[str, int]] = {}
    for lines in stat_lines_by_position.values():
        for (_name, line_week), stat_line in lines.items():
            team = stat_line.get("team") or ""
            if not team:
                continue
            entry = totals.setdefault(
                (team, line_week), {"targets": 0, "rush_att": 0, "receptions": 0, "pass_att": 0}
            )
            entry["targets"] += stat_line.get("targets", 0)
            entry["rush_att"] += stat_line.get("rush_att", 0)
            entry["receptions"] += stat_line.get("receptions", 0)
            entry["pass_att"] += stat_line.get("pass_att", 0)
    return totals


def compute_touches(stat_line: dict[str, int | float | str]) -> int | None:
    """rush_att + receptions -- None (not 0) when the stat line has no
    "rush_att" key at all, meaning this position's file simply has no
    line for this player/week (missing file, bye, etc.) rather than a
    real 0-touch performance."""
    if "rush_att" not in stat_line:
        return None
    return stat_line.get("rush_att", 0) + stat_line.get("receptions", 0)


def compute_share_pcts(
    stat_line: dict[str, int | float | str],
    team_totals: dict[tuple[str, int], dict[str, int]],
    team: str,
    week: int,
) -> tuple[float | None, float | None, float | None]:
    """(target_share_pct, touch_share_pct, opp_share_pct) -- see this
    module's own docstring for each metric's exact formula. All three are
    None when that team total itself isn't available (that position's
    stat file missing, or nobody on this team recorded a line at all that
    week). target_share_pct is additionally None whenever `stat_line` has
    no "targets" key at all -- QB, always, since no FantasyData file
    carries a QB's own targets (touch_share_pct and opp_share_pct don't
    get this same treatment: a QB's missing targets/receptions simply
    contribute 0 to their own numerator, same as compute_touches already
    does for a QB's missing receptions, so those two metrics stay
    meaningful -- carries-only shares -- for a QB instead of going None).

    Joined on the stat line's OWN team (`stat_line.get("team")`), not
    whatever `team` the caller passes in -- `team_totals` is built
    entirely from that same FantasyData source, so this guarantees a
    match even if some other source (e.g. the DK Players tracker) ever
    spells a team differently (e.g. "LAR" vs. "LA"). Falls back to the
    passed-in `team` only so the lookup has *something* to try when
    `stat_line` is empty (this player has no stat line at all that week)
    -- moot either way, since every value below is already None in that
    case."""
    own_team = stat_line.get("team") or team
    team_total = team_totals.get((own_team, week))
    if team_total is None:
        return None, None, None

    target_share_pct = None
    targets_value = stat_line.get("targets")
    if targets_value is not None and team_total["pass_att"] > 0:
        target_share_pct = round(targets_value / team_total["pass_att"] * 100, 1)

    rush_att = stat_line.get("rush_att", 0)
    receptions = stat_line.get("receptions", 0)
    touch_denominator = team_total["rush_att"] + team_total["receptions"]
    touch_share_pct = None
    if touch_denominator > 0:
        touch_share_pct = round((rush_att + receptions) / touch_denominator * 100, 1)

    targets_for_opp = stat_line.get("targets", 0)
    opp_denominator = team_total["rush_att"] + team_total["targets"]
    opp_share_pct = None
    if opp_denominator > 0:
        opp_share_pct = round((rush_att + targets_for_opp) / opp_denominator * 100, 1)

    return target_share_pct, touch_share_pct, opp_share_pct


def compute_usage_share_updates(
    stat_lines_by_position: dict[str, dict[tuple[str, int], dict[str, int | float | str]]],
    week: int,
) -> dict[str, dict[str, tuple[float | None, float | None, float | None]]]:
    """{position: {player_name: (target_share_pct, touch_share_pct,
    opp_share_pct)}} for every player who has a stat line for `week`,
    across every position present in `stat_lines_by_position` -- the one
    function backend/api/dk_players/calculate_week.py actually calls. Team
    totals (team_usage_totals) are computed once, across every position
    passed in, so a player's share always reflects their team's WHOLE
    offense that week, not just whichever positions happen to already have
    a season file. A position with no rows for `week` (its file exists but
    this week wasn't in it) is simply left out of the result -- there's
    nothing to write back for it."""
    team_totals = team_usage_totals(stat_lines_by_position)
    updates: dict[str, dict[str, tuple[float | None, float | None, float | None]]] = {}
    for position, lines in stat_lines_by_position.items():
        position_updates: dict[str, tuple[float | None, float | None, float | None]] = {}
        for (name, line_week), stat_line in lines.items():
            if line_week != week:
                continue
            team = stat_line.get("team", "")
            position_updates[name] = compute_share_pcts(stat_line, team_totals, team, week)
        if position_updates:
            updates[position] = position_updates
    return updates


_SHARE_PCT_FIELDS = ("target_share_pct", "touch_share_pct", "opp_share_pct")


def compute_share_deltas(
    current: dict | None, prior: dict | None
) -> dict[str, float | None]:
    """Compute week-over-week deltas for the three share-pct fields.

    Mirrors the current-vs-(week-1) comparison already used by
    game_preview_player_tags.py's _share_trend_tags(): for each of
    target_share_pct/touch_share_pct/opp_share_pct, returns
    current - prior as a raw (unrounded) float, or None when either
    side is missing the field or isn't numeric (e.g. no prior-week
    stat line at all, such as a player's first game or a bye-week
    gap making week-1 unavailable).
    """
    deltas: dict[str, float | None] = {}
    for field in _SHARE_PCT_FIELDS:
        current_val = current.get(field) if current else None
        prior_val = prior.get(field) if prior else None
        if isinstance(current_val, (int, float)) and isinstance(prior_val, (int, float)):
            deltas[f"{field.removesuffix('_pct')}_delta"] = current_val - prior_val
        else:
            deltas[f"{field.removesuffix('_pct')}_delta"] = None
    return deltas
