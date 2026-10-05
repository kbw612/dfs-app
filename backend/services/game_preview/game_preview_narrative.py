"""
Game Preview Phase C -- one auto-generated, deterministic set of sections
per game, combining Phase A's team-level context (Vegas/O-line-D-line
matchup) with Phase B's own player tags. Fully rule-based, same philosophy
as every Phase B tag (see game_preview_player_tags.py's own module
docstring and this feature's original scoping decision: fully rule-based,
no manual override) -- this module carries that same "fixed threshold, no
LLM free-form prose" spirit up to the summary layer. Every entry is built
from a plain string template over already-computed fields; nothing here
calls out to a model.

A GamePreviewNarrativeSection is either a single flat bullet with no
heading (label=None -- used only for the Vegas line) or a labeled
sub-list ("O vs D Line Matchup", "Offensive Pace", "Matchup Trends",
"Ownership", "Plays to consider", "Fade", "Monitor") with one entry per line
under that heading. Weather is deliberately NOT one of these sections -- it's
rendered as its own dedicated final line by the frontend (colored by
GamePreviewGame.weather.color, same "color column" treatment as the
Weather tab's own cards), reading straight off GamePreviewGame.weather
rather than being turned into a section here, so it can't end up stated
twice.

Most sections are independently optional -- included only when their own
underlying data clears a notability bar (see each _*_section helper's own
docstring) -- so a game with, say, no notable positional matchup on either
side simply contributes no "Matchup Trends" section at all rather than an
empty one. Two sections are the exception and always appear once their raw
data exists at all, not gated behind any notability bar: "O vs D Line
Matchup" (see _ol_dl_matchup_line's own docstring for why the old
notability gate was removed) and "Offensive Pace" (this now always states
both teams' current pass/run rate split, only the trend note on top of
that is gated). A game with no notable signal in any category still gets one real
fallback section (see build_game_narrative's own docstring) rather than an
empty list, mirroring the player tags' own "no signal, no row" spirit just
phrased as a single fallback bullet instead of an absent list entry.
"""

from __future__ import annotations

from backend.schemas.game_preview.game_preview import (
    GamePreviewDstMatchup,
    GamePreviewNarrativeSection,
    GamePreviewTeamSide,
    GamePreviewVegas,
)

# -- Ownership section icons -- a team's own combined projected ownership
# (see GamePreviewTeamSide.projected_ownership_pct), and separately a whole
# game's own combined_projected_ownership_pct, each get flagged Low/High Own
# based on THIS WEEK's own 33rd/67th percentile ranking (see
# game_preview_matchups.py's compute_ownership_bands/classify_by_bands)
# rather than a fixed absolute percentage -- what counts as "low
# owned" shifts slate to slate. Both are the game-environment-leverage angle
# from this feature's own framing, not a repeat of the per-player leverage/
# chalk tags (see game_preview_player_tags.py's own _ownership_tag) which
# already cover the player-level signal.
LOW_OWNERSHIP_ICON = "\U0001f4c9"  # 📉
HIGH_OWNERSHIP_ICON = "\U0001f4c8"  # 📈

# Same icon + label text as the top-center Game Preview card badge (see
# GamePreviewView.tsx's own "game-preview-high-ou-badge"/"game-preview-low-
# ou-badge" spans) -- reused verbatim here so the very first bullet of the
# Ownership section echoes that same call-out rather than inventing a
# differently-worded one. Only one can ever fire (see is_high_over_under/
# is_low_over_under's own non-overlapping thresholds).
HIGH_OVER_UNDER_FLAG_LINE = "\U0001f525 High O/U"  # 🔥 High O/U
LOW_OVER_UNDER_FLAG_LINE = "❄️ Low O/U"  # ❄️ Low O/U

# Which tag kinds get their own narrative section, in this order, and the
# label each one is introduced with. "leverage"/"chalk" are deliberately
# left out of the narrative itself (they're ownership-only signals, not a
# play/fade/monitor call) -- they still show on each player's own tag list
# in the Phase B player view, just not narrated here.
_NARRATED_TAG_KINDS = (
    ("play", "Plays to consider"),
    ("fade", "Fade"),
    ("monitor", "Monitor"),
)


def _format_number(value: float) -> str:
    """Trims a trailing ".0" (44.0 -> "44") but keeps a real decimal
    (44.5 -> "44.5") -- matches how a person would actually write a whole
    total/spread by hand rather than always showing one decimal place."""
    return f"{value:g}"


def _vegas_section(
    label: str,
    away_team: str,
    home_team: str,
    vegas: GamePreviewVegas | None,
    high_over_under: bool = False,
    low_over_under: bool = False,
) -> GamePreviewNarrativeSection | None:
    """None unless there's at least an over/under to report -- a
    kickoff-only or fully-empty GamePreviewVegas (see that schema's own
    docstring on why every field can be independently None) has nothing
    worth narrating on its own. Rendered as "{O/U} O/U (AWAY total - HOME
    total)" -- no repeated game label (that's already the card's own
    header) and no "-point total" phrasing. This is also the game's first
    bullet overall (see build_game_narrative's own ordering docstring), so
    when the game is flagged, the High/Low O/U flag (see
    HIGH_OVER_UNDER_FLAG_LINE/LOW_OVER_UNDER_FLAG_LINE, same icon+label as
    the card's own top-center badge used to be) leads that same single
    bullet as a space-separated prefix (e.g. "\U0001f525 High O/U 49.5 O/U
    (...)") rather than repeating inside the separate Ownership section
    below, or appearing as its own second bullet -- is_high_over_under/
    is_low_over_under (game_preview_matchups.py) both require over_under to
    be set, so this section always exists whenever either flag could be
    True."""
    if vegas is None or vegas.over_under is None:
        return None
    if vegas.away_implied_total is not None and vegas.home_implied_total is not None:
        text = (
            f"{_format_number(vegas.over_under)} O/U "
            f"({away_team} {_format_number(vegas.away_implied_total)} - "
            f"{home_team} {_format_number(vegas.home_implied_total)})"
        )
    else:
        text = f"{_format_number(vegas.over_under)} O/U"
    if high_over_under:
        text = f"{HIGH_OVER_UNDER_FLAG_LINE} {text}"
    elif low_over_under:
        text = f"{LOW_OVER_UNDER_FLAG_LINE} {text}"
    return GamePreviewNarrativeSection(label=None, entries=[text])


def _ol_dl_matchup_line(team: str, opponent: str, matchup: GamePreviewDstMatchup | None) -> str | None:
    """None only when there's no trailing-window matchup data at all for
    this team (week 1, or no DST stat lines yet -- see
    GamePreviewDstMatchup's own docstring) -- always included once that
    data exists, regardless of how big the numbers are. This USED to gate
    on a sacks/takeaways notability threshold the same way the old "DST"
    section did, but that dropped one side's own line whenever ITS numbers
    alone were unremarkable, even though this is inherently a two-sided
    comparison (e.g. an ARI @ SF game showed only ARI's line because SF's
    own forcing numbers didn't clear the bar, which read as a missing
    bullet rather than "SF's D-line has been average this year" -- a real,
    still-useful data point). Framed as this team's own D-LINE (via its
    DST's own sacks/takeaways forced) against the opponent's own O-LINE
    (that offense's own sacks/takeaways allowed) -- same underlying DST
    Trends numbers as the old "DST" framing, just described as the O-line/
    D-line matchup directly rather than talking about "this team's DST.\""""
    if matchup is None:
        return None
    return (
        f"{team}'s D-line has forced {matchup.sacks_per_game_forced:.1f} sacks and "
        f"{matchup.takeaways_per_game_forced:.1f} takeaways/game; {opponent}'s O-line has allowed "
        f"{matchup.opponent_sacks_per_game_allowed:.1f} sacks and "
        f"{matchup.opponent_takeaways_per_game_allowed:.1f} takeaways/game."
    )


def _ol_dl_matchup_section(away: GamePreviewTeamSide, home: GamePreviewTeamSide) -> GamePreviewNarrativeSection | None:
    """One "O vs D Line Matchup" section holding both sides' own lines (away
    then home) -- None entirely only when NEITHER side has any
    trailing-window DST-trend data yet (week 1, or DST weekly stats not
    uploaded); once either side has data, its own line always appears (see
    _ol_dl_matchup_line's own docstring for why this isn't gated further)."""
    lines = []
    for side, opponent_team in ((away, home.team), (home, away.team)):
        line = _ol_dl_matchup_line(side.team, opponent_team, side.dst_matchup)
        if line is not None:
            lines.append(line)
    if not lines:
        return None
    return GamePreviewNarrativeSection(label="O vs D Line Matchup", entries=lines)


def _pace_section(away: GamePreviewTeamSide, home: GamePreviewTeamSide) -> GamePreviewNarrativeSection | None:
    """One "Offensive Pace" section -- None entirely only when NEITHER side
    has any pace-trend data at all yet (week 1, or no weekly stats
    uploaded). Deliberately carries no text bullets of its own (`entries`
    is always []) -- this used to state each team's current pass/run rate
    split in prose, but that's now redundant with the frontend's own
    weeks-as-columns pace trend table (GamePreviewTeamSide.pace_trend.trailing),
    which the frontend nests directly under this same heading and which
    already shows the same numbers (plus every other week in the window,
    plus each week's own opponent and deltas) in a denser, more scannable
    form. This function's only remaining job is deciding whether the
    heading (and therefore the table) should appear at all."""
    if away.pace_trend is None and home.pace_trend is None:
        return None
    return GamePreviewNarrativeSection(label="Offensive Pace", entries=[])


def _matchup_trends_lines(team: str, opponent: str, side: GamePreviewTeamSide) -> list[str]:
    """[] when `side`'s own defense has no exploitable positions this
    window (the common case -- see GamePreviewPositionalMatchup's own
    docstring for the two-part rule). One line PER qualifying position
    (not one combined line naming every position), each carrying the same
    FPTS-allowed/league-avg/high-multiplier-games numbers the matching
    player tag itself uses (see game_preview_player_tags.py's own
    _positional_matchup_tag) -- so this section explains the number behind
    the tag rather than just repeating the position name."""
    lines = []
    for signal in side.exploitable_positions:
        lines.append(
            f"{team} has allowed {signal.avg_fpts_allowed:.1f} FPTS/game to {signal.position}s (league avg "
            f"{signal.league_avg_fpts:.1f}) with {signal.high_multiplier_games} high-multiplier games over "
            f"{signal.games} games -- consider {opponent}'s {signal.position}s."
        )
    return lines


def _matchup_trends_section(away: GamePreviewTeamSide, home: GamePreviewTeamSide) -> GamePreviewNarrativeSection | None:
    """One "Matchup Trends" section holding both sides' own exploitable-
    position lines (away's defense's positions, then home's defense's
    positions) -- None entirely if neither side has any."""
    lines = [
        *_matchup_trends_lines(away.team, home.team, away),
        *_matchup_trends_lines(home.team, away.team, home),
    ]
    if not lines:
        return None
    return GamePreviewNarrativeSection(label="Matchup Trends", entries=lines)


def _tag_section(kind: str, label: str, away: GamePreviewTeamSide, home: GamePreviewTeamSide) -> GamePreviewNarrativeSection | None:
    """None when neither side has a single player with a fired tag of this
    kind. Names are taken in each side's own players list order (already
    alphabetical -- see build_team_player_tags), away side first -- every
    player with a fired tag of this kind gets a line, uncapped (an earlier
    3-name cap crowded out real signals purely by alphabetical accident --
    e.g. a positional-matchup "play" tag on a player whose name happened to
    sort after 3 other, unrelated "play" tags never made the list even
    though the signal itself had fired correctly). One player per entry
    (not joined into one line) so each gets its own bullet."""
    entries = [f"{p.name} ({t.reason})" for side in (away, home) for p in side.players for t in p.tags if t.kind == kind]
    if not entries:
        return None
    return GamePreviewNarrativeSection(label=label, entries=entries)


def _ownership_icon_for_flag(flag: str | None) -> str:
    """"" (nothing) unless `flag` is "low" or "high" -- shared by every
    piece of the combined ownership bullet (see _ownership_combined_line) so
    a flag of None never accidentally prefixes anything."""
    if flag == "low":
        return LOW_OWNERSHIP_ICON
    if flag == "high":
        return HIGH_OWNERSHIP_ICON
    return ""


def _ownership_combined_line(
    away_team: str,
    away_projected_ownership_pct: float | None,
    away_ownership_flag: str | None,
    home_team: str,
    home_projected_ownership_pct: float | None,
    home_ownership_flag: str | None,
    combined_projected_ownership_pct: float | None,
    combined_ownership_flag: str | None,
) -> str | None:
    """One combined bullet for both teams' own projected ownership plus the
    game's own combined total -- replaces what used to be two separate
    per-team lines, e.g. "\U0001f4c8 52.3% projected ownership = \U0001f4c9
    ARI 15.8% + SF 36.5%" (combined total leads, per-team breakdown follows).
    Each of the three numbers (away/home/combined) gets its own
    icon prefix (LOW_OWNERSHIP_ICON/HIGH_OWNERSHIP_ICON) when this week's
    own band ranking flagged it Low/High Own (see game_preview_matchups
    .py's compute_ownership_bands/classify_by_bands -- the flags are
    computed once per week by the engine and passed in here already
    resolved, since ranking needs every game's/team's numbers at once, not
    just this one game's); a value that's neither gets no icon. None only
    when there's no ownership data at all for this game (both team
    percentages AND the combined percentage are all None) -- a side missing
    just its OWN pct is treated as 0.0% in the combined arithmetic, same
    "missing side treated as 0" convention the old ratio line used."""
    if away_projected_ownership_pct is None and home_projected_ownership_pct is None and combined_projected_ownership_pct is None:
        return None
    away_pct = away_projected_ownership_pct or 0.0
    home_pct = home_projected_ownership_pct or 0.0
    combined_pct = combined_projected_ownership_pct if combined_projected_ownership_pct is not None else away_pct + home_pct
    away_icon = _ownership_icon_for_flag(away_ownership_flag)
    home_icon = _ownership_icon_for_flag(home_ownership_flag)
    combined_icon = _ownership_icon_for_flag(combined_ownership_flag)
    away_part = f"{away_icon} {away_team} {away_pct:.1f}%" if away_icon else f"{away_team} {away_pct:.1f}%"
    home_part = f"{home_icon} {home_team} {home_pct:.1f}%" if home_icon else f"{home_team} {home_pct:.1f}%"
    combined_part = f"{combined_icon} {combined_pct:.1f}%" if combined_icon else f"{combined_pct:.1f}%"
    return f"{combined_part} projected ownership = {away_part} + {home_part}"


def _ratio_line(
    combined_projected_ownership_pct: float | None,
    over_under: float | None,
    total_to_ownership_ratio: float | None,
    high_over_under: bool,
    low_over_under: bool,
) -> str | None:
    """None unless all three of combined ownership/O-U/ratio are available
    (see game_preview_matchups.py's total_to_ownership_ratio for exactly
    when that's None). Deliberately doesn't restate the away/home/combined
    percentages -- that breakdown now lives in _ownership_combined_line,
    directly above this line in the section -- so this one just states the
    O/U-leverage angle itself: the ratio, on what total, with a "high-total
    game" note when `high_over_under` is True (O/U >= HIGH_OVER_UNDER_PCT,
    47.0) or a "low-total game" note when `low_over_under` is True (O/U <=
    LOW_OVER_UNDER_PCT, 40.0) -- these two never both fire at once (see
    is_high_over_under/is_low_over_under's own non-overlapping thresholds)."""
    if combined_projected_ownership_pct is None or over_under is None or total_to_ownership_ratio is None:
        return None
    if high_over_under:
        note = " -- a high-total game (O/U 47+)"
    elif low_over_under:
        note = " -- a low-total game (O/U 40 or under)"
    else:
        note = ""
    return (
        f"Game Total-to-Ownership Ratio: {total_to_ownership_ratio:.2f}% ownership per O/U point on a "
        f"{_format_number(over_under)} O/U{note}."
    )


def _ownership_section(
    away: GamePreviewTeamSide,
    home: GamePreviewTeamSide,
    away_ownership_flag: str | None,
    home_ownership_flag: str | None,
    combined_projected_ownership_pct: float | None,
    combined_ownership_flag: str | None,
    over_under: float | None,
    total_to_ownership_ratio: float | None,
    high_over_under: bool,
    low_over_under: bool,
) -> GamePreviewNarrativeSection | None:
    """One "Ownership" section combining two independent signals -- one
    combined bullet for both sides' own ownership plus the game's own
    combined total (see _ownership_combined_line, always included once any
    ownership data exists), and this game's own Total-to-Ownership Ratio
    (see _ratio_line, whole-game, always included once its inputs exist).
    The High/Low O/U flag line used to lead this section too, but now rides
    along on the game's own Vegas bullet instead (see _vegas_section) --
    it's still passed high_over_under/low_over_under here because
    _ratio_line's own phrasing calls out a high/low O/U game. None entirely
    only when neither of the two has anything to say (no ownership data
    loaded for this game at all)."""
    lines = []
    combined_line = _ownership_combined_line(
        away.team,
        away.projected_ownership_pct,
        away_ownership_flag,
        home.team,
        home.projected_ownership_pct,
        home_ownership_flag,
        combined_projected_ownership_pct,
        combined_ownership_flag,
    )
    if combined_line is not None:
        lines.append(combined_line)
    ratio_line = _ratio_line(
        combined_projected_ownership_pct,
        over_under,
        total_to_ownership_ratio,
        high_over_under,
        low_over_under,
    )
    if ratio_line is not None:
        lines.append(ratio_line)
    if not lines:
        return None
    return GamePreviewNarrativeSection(label="Ownership", entries=lines)


def build_game_narrative(
    label: str,
    away: GamePreviewTeamSide,
    home: GamePreviewTeamSide,
    vegas: GamePreviewVegas | None,
    combined_projected_ownership_pct: float | None = None,
    total_to_ownership_ratio: float | None = None,
    high_over_under: bool = False,
    low_over_under: bool = False,
    away_ownership_flag: str | None = None,
    home_ownership_flag: str | None = None,
    combined_ownership_flag: str | None = None,
) -> list[GamePreviewNarrativeSection]:
    """A handful of sections for this one game. Order: Vegas (O/U), Ownership,
    Pace, O vs D Line Matchup (both sides combined), Matchup Trends, then
    Play/Fade/Monitor tag call-outs -- per an explicit reorder request
    putting O/U and Ownership (the two market/computed-signal bullets) up
    front, ahead of the on-field context sections. Weather is NOT included
    here -- see this module's own docstring for why it's rendered
    separately by the frontend instead.

    The seven ownership params all default to None/False (rather than
    required) so a Phase-A/B/C-era caller/test that doesn't compute them
    keeps working unchanged -- they just never get an "Ownership" section,
    same graceful-degradation convention as everywhere else in this
    feature. game_preview_engine.py's own build_game_preview always passes
    them (see game_preview_matchups.py's combined_projected_ownership_pct/
    total_to_ownership_ratio/is_high_over_under/is_low_over_under, plus the
    three *_ownership_flag params, each already resolved by the engine via
    compute_ownership_bands/classify_by_bands against this WEEK's
    own set of team/game ownership numbers -- narrative building itself
    stays a pure per-game function, it doesn't rank across games).

    A game with no notable section in any category still returns a list
    with one real (if generic) fallback section (label=None, one entry)
    naming the game, rather than an empty list -- an empty section list
    would look like a rendering bug on the frontend, not "nothing notable
    this week.\""""
    sections: list[GamePreviewNarrativeSection] = []

    vegas_section = _vegas_section(label, away.team, home.team, vegas, high_over_under, low_over_under)
    if vegas_section is not None:
        sections.append(vegas_section)

    ownership_section = _ownership_section(
        away,
        home,
        away_ownership_flag,
        home_ownership_flag,
        combined_projected_ownership_pct,
        combined_ownership_flag,
        vegas.over_under if vegas is not None else None,
        total_to_ownership_ratio,
        high_over_under,
        low_over_under,
    )
    if ownership_section is not None:
        sections.append(ownership_section)

    pace_section = _pace_section(away, home)
    if pace_section is not None:
        sections.append(pace_section)

    ol_dl_section = _ol_dl_matchup_section(away, home)
    if ol_dl_section is not None:
        sections.append(ol_dl_section)

    matchup_trends_section = _matchup_trends_section(away, home)
    if matchup_trends_section is not None:
        sections.append(matchup_trends_section)

    for kind, tag_label in _NARRATED_TAG_KINDS:
        tag_section = _tag_section(kind, tag_label, away, home)
        if tag_section is not None:
            sections.append(tag_section)

    if not sections:
        return [
            GamePreviewNarrativeSection(
                label=None, entries=[f"No notable Vegas, O vs D Line matchup, or player-tag signals yet for {label}."]
            )
        ]
    return sections
