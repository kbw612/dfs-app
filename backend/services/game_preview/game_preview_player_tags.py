"""
Game Preview Phase B -- per-player Play/Fade/Monitor/Leverage/Chalk tags,
one independent rule check per signal (see the person's own answers when
this feature was scoped: Multipliers trends, usage share trends,
injury-driven usage bumps, and ownership all count; fully rule-based, no
manual override). Every threshold here is a fixed constant, same
"document the exact band" convention Breakout Watch already established on
the Multipliers tab -- there's no adjustable field, per that scoping
decision.

Reuses existing engines wherever the signal already has one, rather than
re-deriving it:
  - Multipliers trends (Repeat Performer / Breakout Watch) -- calls
    build_multiplier_rows() (the exact same engine behind the Multipliers
    tab) and re-applies that tab's own trend rules in Python (see
    MultipliersView.tsx's REPEAT_PERFORMER_*/BREAKOUT_WATCH_* constants --
    mirrored here so the two stay in lockstep).
  - Injury-driven usage bumps -- calls compute_usage_bumps() (the Usage
    Bump Players engine) directly; that module already resolves "is the
    trigger actually out this week" and scores every beneficiary, so
    there's nothing left for this module to recompute.
  - Usage share trend and Ownership have no existing per-player engine to
    reuse, so their rules are new, small, and documented inline below.

A player needs only ONE fired rule to appear at all -- see
GamePreviewPlayer's own "no signal, no row" docstring.
"""

from __future__ import annotations

from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_preview.game_preview import GamePreviewPlayer, GamePreviewPlayerTag, GamePreviewPositionalMatchup
from backend.schemas.multipliers.multipliers import MultiplierRow
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.usage_bump.usage_bump import UsageBump
from backend.services.multipliers.multipliers_engine import build_multiplier_rows
from backend.services.schedule.schedule_loader import ScheduleRow
from backend.services.shared.usage_shares import compute_share_deltas

# -- Multipliers trends (mirrors MultipliersView.tsx's own constants) --
REPEAT_PERFORMER_HIGH_THRESHOLD = 4.0
REPEAT_PERFORMER_MIN_HIGH_WEEKS = 2
BREAKOUT_WATCH_NON_TD_MULT_MIN = 2.5
BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE = 4.0
BREAKOUT_WATCH_MIN_HIGH_WEEKS = 2

# -- Usage share trend (new to this tab) -- a rise/fall of at least this
# many percentage points between the two most recently played weeks shown
# (base week vs. the week before it) counts as a real trend, not noise.
SHARE_TREND_THRESHOLD_PCT = 5.0

# -- Ownership (new to this tab) -- fixed low/high bands, same spirit as
# Ownership Summary's own "chalk"/leverage framing but as flat cutoffs
# rather than a slate-relative computation, since this tab has no per-slate
# context of its own to compute a relative leverage point from.
LOW_OWNERSHIP_THRESHOLD_PCT = 5.0
HIGH_OWNERSHIP_THRESHOLD_PCT = 25.0

_SHARE_FIELD_LABELS = {
    "target_share_pct": "target share",
    "touch_share_pct": "touch share",
    "opp_share_pct": "opportunity share",
}

# Maps compute_share_deltas' own output keys (see usage_shares.py) back to
# the _SHARE_FIELD_LABELS/stat-line field names above -- that helper's keys
# are "<field>_delta" with "_pct" already stripped, rather than the raw
# "target_share_pct" spelling used here.
_DELTA_KEY_TO_FIELD = {
    "target_share_delta": "target_share_pct",
    "touch_share_delta": "touch_share_pct",
    "opp_share_delta": "opp_share_pct",
}


def _multiplier_sequence(row: MultiplierRow) -> list[float | None]:
    return [row.multiplier, *[t.multiplier for t in row.trailing]]


def _non_td_multiplier_sequence(row: MultiplierRow) -> list[float | None]:
    return [row.non_td_multiplier, *[t.non_td_multiplier for t in row.trailing]]


def _td_fpts_sequence(row: MultiplierRow) -> list[float | None]:
    return [row.td_fpts, *[t.td_fpts for t in row.trailing]]


def _multiplier_tags(row: MultiplierRow) -> list[GamePreviewPlayerTag]:
    tags: list[GamePreviewPlayerTag] = []

    mult_seq = _multiplier_sequence(row)
    # Denominator is how many of those weeks the player actually has a
    # tracker row for (None entries are bye/not-yet-rostered/not-yet-
    # backfilled weeks, not weeks that "didn't count"), not the nominal
    # window size (base week + trailing_weeks) -- early in a season, most
    # of that nominal window hasn't been played yet at all, so phrasing it
    # as "2 of the last 6 weeks" when only 2 weeks have actually been
    # played is misleading (it reads as a 2-for-6 rate when it's really
    # 2-for-2). Counting only real weeks gives "2 of the last 2 weeks"
    # instead, which is what actually happened.
    played_weeks = [v for v in mult_seq if v is not None]
    high_mult_weeks = [v for v in played_weeks if v >= REPEAT_PERFORMER_HIGH_THRESHOLD]
    if len(high_mult_weeks) >= REPEAT_PERFORMER_MIN_HIGH_WEEKS:
        tags.append(
            GamePreviewPlayerTag(
                kind="fade",
                reason=(
                    f"Repeat Performer -- {len(high_mult_weeks)} of the last {len(played_weeks)} weeks played at "
                    f"{REPEAT_PERFORMER_HIGH_THRESHOLD}x+ Multiplier, price has likely caught up"
                ),
            )
        )

    non_td_seq = _non_td_multiplier_sequence(row)
    td_seq = _td_fpts_sequence(row)
    high_breakout_weeks = sum(
        1
        for i, v in enumerate(non_td_seq)
        if v is not None
        and BREAKOUT_WATCH_NON_TD_MULT_MIN <= v < BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE
        and td_seq[i] == 0
    )
    if high_breakout_weeks >= BREAKOUT_WATCH_MIN_HIGH_WEEKS:
        tags.append(
            GamePreviewPlayerTag(
                kind="play",
                reason=(
                    f"Breakout Watch -- {high_breakout_weeks} weeks with a "
                    f"{BREAKOUT_WATCH_NON_TD_MULT_MIN}-{BREAKOUT_WATCH_NON_TD_MULT_MAX_EXCLUSIVE} non-TD "
                    "multiplier and 0 TD FPTS that week -- real volume that hasn't paid off with a TD yet"
                ),
            )
        )

    return tags


def _share_trend_tags(
    name: str,
    position: str,
    base_week: int,
    stat_lines_by_position: dict[str, dict[tuple[str, int], dict[str, int | float | str]]],
) -> list[GamePreviewPlayerTag]:
    """Compares the base week's own share fields against the week before it
    -- a rise/fall of >= SHARE_TREND_THRESHOLD_PCT percentage points in
    target share, touch share, or opp share counts as a real trend. Only
    the single largest rise and single largest fall are reported (not one
    tag per field) so a player with three noisy-but-small share moves
    doesn't drown out one with one real, large move."""
    lines = stat_lines_by_position.get(position, {})
    current = lines.get((name, base_week))
    prior = lines.get((name, base_week - 1))
    if current is None or prior is None:
        return []

    # compute_share_deltas() (see usage_shares.py) is a small shared
    # current-vs-prior diff helper -- reuse it here rather than re-deriving
    # the same math inline.
    share_deltas = compute_share_deltas(current, prior)
    deltas: list[tuple[str, float, float, float]] = []  # (field, prior, current, delta)
    for delta_key, field in _DELTA_KEY_TO_FIELD.items():
        delta = share_deltas[delta_key]
        if delta is None:
            continue
        c = current.get(field)
        p = prior.get(field)
        deltas.append((field, float(p), float(c), delta))

    if not deltas:
        return []

    tags: list[GamePreviewPlayerTag] = []
    biggest_rise = max(deltas, key=lambda d: d[3])
    if biggest_rise[3] >= SHARE_TREND_THRESHOLD_PCT:
        field, prior_val, current_val, _ = biggest_rise
        tags.append(
            GamePreviewPlayerTag(
                kind="play",
                reason=f"Rising {_SHARE_FIELD_LABELS[field]} -- {prior_val:.1f}% to {current_val:.1f}% week-over-week",
            )
        )
    biggest_fall = min(deltas, key=lambda d: d[3])
    if biggest_fall[3] <= -SHARE_TREND_THRESHOLD_PCT:
        field, prior_val, current_val, _ = biggest_fall
        tags.append(
            GamePreviewPlayerTag(
                kind="monitor",
                reason=f"Falling {_SHARE_FIELD_LABELS[field]} -- {prior_val:.1f}% to {current_val:.1f}% week-over-week",
            )
        )
    return tags


# A status in this group means the player is confirmed not playing (not
# just at risk) -- same "O" group codes as frontend/src/statusCodes.ts's
# own STATUS_FILTER_GROUPS, kept as a local copy since this is backend
# code. Q/D triggers keep the "if ... sits" hedge below, since a
# Questionable/Doubtful player might still suit up; an Out-group trigger
# gets definite "with ... out" phrasing instead, since "if he sits" reads
# as a hypothetical for a player who's already confirmed out.
_OUT_STATUS_CODES = {"O", "IR", "IR-R", "SUS", "PUP", "NFI", "CEL", "EX", "COV"}


def _usage_bump_tag(bump: UsageBump) -> GamePreviewPlayerTag:
    trigger = bump.causes[0]
    extra = f" (+{len(bump.causes) - 1} more)" if len(bump.causes) > 1 else ""
    if trigger.status in _OUT_STATUS_CODES:
        reason = f"Usage bump with {trigger.player} ({trigger.status}) out{extra} -- extra volume likely"
    else:
        reason = f"Usage bump if {trigger.player} ({trigger.status}) sits{extra} -- extra volume likely"
    return GamePreviewPlayerTag(kind="play", reason=reason)


def _positional_matchup_tag(
    position: str, opponent: str, exploitable_positions: list[GamePreviewPositionalMatchup]
) -> GamePreviewPlayerTag | None:
    """Fires when `opponent`'s own defense has been a soft matchup for this
    player's own position -- see game_preview_matchups.py's
    build_positional_matchup_signals for the exact two-part rule (above-
    average FPTS allowed AND multiple high-multiplier games allowed, both
    required, over the trailing window). `exploitable_positions` is already
    scoped to the opponent's own team by the caller."""
    for signal in exploitable_positions:
        if signal.position == position:
            return GamePreviewPlayerTag(
                kind="play",
                reason=(
                    f"{opponent} has allowed {signal.avg_fpts_allowed:.1f} FPTS/game to {position}s (league avg "
                    f"{signal.league_avg_fpts:.1f}) with {signal.high_multiplier_games} high-multiplier games over "
                    f"the last {signal.games} games"
                ),
            )
    return None


def _ownership_tag(player: OwnershipPlayer) -> GamePreviewPlayerTag | None:
    if player.ownership_pct is None:
        return None
    if player.ownership_pct <= LOW_OWNERSHIP_THRESHOLD_PCT:
        return GamePreviewPlayerTag(
            kind="leverage", reason=f"Low projected ownership ({player.ownership_pct:.1f}%) -- leverage upside"
        )
    if player.ownership_pct >= HIGH_OWNERSHIP_THRESHOLD_PCT:
        return GamePreviewPlayerTag(
            kind="chalk", reason=f"High projected ownership ({player.ownership_pct:.1f}%) -- expect heavy usage in lineups"
        )
    return None


def build_team_player_tags(
    team: str,
    tracker_rows: list[DkPlayerRow],
    schedule_rows: list[ScheduleRow],
    week: int,
    window_weeks: int,
    stat_lines_by_position: dict[str, dict[tuple[str, int], dict[str, int | float | str]]],
    ownership_players: list[OwnershipPlayer],
    usage_bumps: list[UsageBump],
    depth_by_name: dict[str, int] | None = None,
    opponent: str = "",
    opponent_exploitable_positions: list[GamePreviewPositionalMatchup] | None = None,
) -> list[GamePreviewPlayer]:
    """One GamePreviewPlayer per name that had at least one signal fire,
    for this one team. Player universe is the UNION of three independent
    sources rather than just one, since no single source covers every kind
    of signal a beneficiary might only show up in:

    - Multipliers' own base-week roster (via build_multiplier_rows, scoped
      to this team) -- covers Repeat Performer/Breakout Watch/share trend.
    - Usage Bump Players' beneficiaries for this team -- a backup who
      benefits from an injury may have had 0 FPTS last week and so never
      appears in Multipliers' own roster at all (that engine skips 0-FPTS
      rows -- see build_multiplier_rows' own docstring), but is exactly
      the kind of player this signal exists to surface.
    - Ownership for this team -- independent of past production entirely.

    `depth_by_name` (player name -> 1-indexed depth-chart rank, already
    scoped to this one team by the caller) fills in each GamePreviewPlayer.
    depth for display (e.g. "WR1", "WR4") -- optional and defaults to
    empty, so a caller with no depth-chart snapshot at all just gets every
    player's depth back as None, same graceful-degradation convention as
    every other optional input here.

    `opponent`/`opponent_exploitable_positions` (optional, default ""/None)
    are this team's own opponent's name and the list of positions THAT
    opponent's own defense has been a soft matchup for (see
    game_preview_matchups.py's build_positional_matchup_signals) -- fires a
    "play" tag on any of this team's own players whose position is in that
    list (see _positional_matchup_tag). Omitting them (Phase-A/B-era
    callers/tests) simply means this one signal never fires, same
    graceful-degradation convention as every other optional input here.
    """
    depth_by_name = depth_by_name or {}
    opponent_exploitable_positions = opponent_exploitable_positions or []
    multiplier_rows, base_week = build_multiplier_rows(tracker_rows, schedule_rows, week, window_weeks, {team})
    multiplier_by_name = {r.name: r for r in multiplier_rows}
    bump_by_name = {u.player: u for u in usage_bumps if u.team_abbrev == team}
    ownership_by_name = {p.player: p for p in ownership_players if p.team == team}

    names = set(multiplier_by_name) | set(bump_by_name) | set(ownership_by_name)

    players: list[GamePreviewPlayer] = []
    for name in names:
        row = multiplier_by_name.get(name)
        bump = bump_by_name.get(name)
        own = ownership_by_name.get(name)
        position = row.position if row is not None else (bump.position if bump is not None else (own.position if own is not None else ""))

        tags: list[GamePreviewPlayerTag] = []
        if row is not None:
            tags.extend(_multiplier_tags(row))
            tags.extend(_share_trend_tags(name, position, base_week, stat_lines_by_position))
        if bump is not None and bump.bump_score > 0:
            tags.append(_usage_bump_tag(bump))
        if own is not None:
            ownership_tag = _ownership_tag(own)
            if ownership_tag is not None:
                tags.append(ownership_tag)
        if position:
            matchup_tag = _positional_matchup_tag(position, opponent, opponent_exploitable_positions)
            if matchup_tag is not None:
                tags.append(matchup_tag)

        if tags:
            players.append(
                GamePreviewPlayer(name=name, position=position, team=team, depth=depth_by_name.get(name), tags=tags)
            )

    players.sort(key=lambda p: p.name)
    return players
