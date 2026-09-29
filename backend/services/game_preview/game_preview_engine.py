"""
Game Preview -- joins this week's own Schedule matchups with three
independent side-channel inputs (Vegas Lines, Weather, Team Default
Factors) plus one trailing-window computation (DST/Off Trends' own
forcing/allowing leaderboards) into one GamePreviewResult -- this is Phase
A, "what does the schedule/market/recent team form say about this game."
Phase B adds one more layer on top: per-player Play/Fade/Monitor/Leverage/
Chalk tags (see game_preview_player_tags.py's own module docstring for the
four independent signals it checks), threaded through via four additional
keyword params (`tracker_rows`, `stat_lines_by_position`,
`ownership_players`, `usage_bumps`) that all default to empty -- a caller
that only wants Phase A's team-level context (or a Phase-A-era test) can
simply omit them and every GamePreviewTeamSide.players list comes back
empty, same graceful-degradation convention as every optional field here.

Phase C adds one more layer: each GamePreviewGame.narrative_sections field,
a handful of deterministic sections combining that game's own Phase A
context and Phase B tags (see game_preview_narrative.py's own module
docstring) -- always computed, never optional, since it's built entirely
from fields already resolved above rather than a new external input that
could be missing. Weather is NOT one of these sections -- see that
module's docstring for why it's surfaced separately, straight off
GamePreviewGame.weather, instead.

Phase D adds a final layer: each GamePreviewTeamSide.injury_groups field
(see game_preview_injuries.py's own module docstring for its groups),
plus a `depth` value (e.g. "WR1", "WR4") on every Phase B
GamePreviewPlayer -- both read from the same optional `depth_chart_
snapshot`/`star_players` inputs, which default to None/empty exactly like
every other Phase B/C side-channel here.

Reuses existing engines/helpers wherever possible rather than
re-implementing their logic: build_dst_trend_leaderboards for the O-line/
D-line matchup piece (same trailing-window/through_week convention DST
Trends already established -- see game_preview_narrative.py's own "O vs D
Line Matchup" section for how this data is now framed), games_for_week/
opponent_and_location for schedule grouping (same as build_game_options),
game_key/game_label/resolve_away_home for the shared "AWAY @ HOME" labeling
convention, build_team_player_tags (game_preview_player_tags.py) for the
whole Phase B computation, build_game_narrative (game_preview_narrative.py)
for the whole Phase C computation, build_team_injury_groups
(game_preview_injuries.py) for the whole Phase D computation, and
team_projected_ownership_pct/combined_projected_ownership_pct/
total_to_ownership_ratio/is_high_over_under/is_low_over_under
(game_preview_matchups.py) for each side's own projected ownership plus the
game-level Total-to-Ownership Ratio/high_over_under/low_over_under flags,
and compute_ownership_bands/classify_by_bands (same module) for the
Low/High Own badges -- these need a two-pass build (see build_game_preview's
own pre_games list) since ranking a team/game's ownership requires every
other team/game's numbers for the week, not just its own.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.dst_trends.dst_trends import DstTrendTeamRow
from backend.schemas.game_preview.game_preview import (
    GamePreviewDstMatchup,
    GamePreviewGame,
    GamePreviewResult,
    GamePreviewTeamFactors,
    GamePreviewTeamSide,
    GamePreviewVegas,
    GamePreviewWeather,
)
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.star_players.star_players import StarPlayersResult
from backend.schemas.usage_bump.usage_bump import UsageBump
from backend.schemas.team_factors.team_factors import TeamFactorEntry
from backend.schemas.vegas_lines.vegas_lines import VegasLinesSnapshot
from backend.schemas.weather.weather import WeatherSnapshot
from backend.services.dst_trends.dst_trends_engine import build_dst_trend_leaderboards
from backend.services.game_preview.game_preview_injuries import build_team_injury_groups
from backend.services.game_preview.game_preview_matchups import (
    build_positional_matchup_signals,
    build_team_pace_trend,
    classify_by_bands,
    combined_projected_ownership_pct as _combined_projected_ownership_pct,
    compute_ownership_bands,
    is_high_over_under,
    is_low_over_under,
    team_projected_ownership_pct,
    total_to_ownership_ratio as _total_to_ownership_ratio,
)
from backend.services.game_preview.game_preview_narrative import build_game_narrative
from backend.services.game_preview.game_preview_player_tags import build_team_player_tags
from backend.services.schedule.schedule_loader import ScheduleRow, games_for_week, opponent_and_location
from backend.services.shared.game_matchup import game_key, game_label, resolve_away_home

_FACTOR_POSITIONS = ("QB", "RB", "WR", "TE", "DST")


def _team_factors(team: str, factors_by_team_position: dict[tuple[str, str], TeamFactorEntry]) -> GamePreviewTeamFactors:
    values: dict[str, float | None] = {}
    for position in _FACTOR_POSITIONS:
        entry = factors_by_team_position.get((team, position))
        values[position.lower()] = entry.factor if entry is not None else None
    return GamePreviewTeamFactors(**values)


def _vegas_for_game(vegas: VegasLinesSnapshot | None, key: str) -> GamePreviewVegas | None:
    if vegas is None:
        return None
    for g in vegas.games:
        if g.game_key == key:
            return GamePreviewVegas(
                over_under=g.current.over_under,
                away_implied_total=g.current.away_implied_total,
                home_implied_total=g.current.home_implied_total,
                kickoff_label=g.kickoff_label,
            )
    return None


def _weather_for_game(weather: WeatherSnapshot | None, key: str) -> GamePreviewWeather | None:
    if weather is None:
        return None
    for g in weather.games:
        if g.game_key == key:
            return GamePreviewWeather(color=g.color, note=g.note)
    return None


def _dst_matchup(team: str, opponent: str, forcing_by_team: dict[str, DstTrendTeamRow], allowing_by_team: dict[str, DstTrendTeamRow]) -> GamePreviewDstMatchup | None:
    """`team`'s own forcing row (its DST's recent sacks/takeaways) paired
    with `opponent`'s own allowing row (that offense's recent sacks/
    turnovers given up) -- None if either side has no row in the trailing
    window (no games played in-window, or the window hasn't started yet --
    see build_dst_trend_leaderboards' own through_week < 1 case, which
    returns empty forcing/allowing lists entirely)."""
    forcing = forcing_by_team.get(team)
    allowing = allowing_by_team.get(opponent)
    if forcing is None or allowing is None:
        return None
    return GamePreviewDstMatchup(
        games=forcing.games,
        sacks_per_game_forced=forcing.sacks_per_game,
        takeaways_per_game_forced=forcing.takeaways_per_game,
        opponent_sacks_per_game_allowed=allowing.sacks_per_game,
        opponent_takeaways_per_game_allowed=allowing.takeaways_per_game,
    )


def build_game_preview(
    season: int,
    week: int,
    schedule_rows: list[ScheduleRow],
    dst_stat_lines: dict[tuple[str, int], dict[str, int | float | str]],
    vegas: VegasLinesSnapshot | None,
    weather: WeatherSnapshot | None,
    factors_by_team_position: dict[tuple[str, str], TeamFactorEntry],
    window_weeks: int = 5,
    tracker_rows: list[DkPlayerRow] | None = None,
    stat_lines_by_position: dict[str, dict[tuple[str, int], dict[str, int | float | str]]] | None = None,
    ownership_players: list[OwnershipPlayer] | None = None,
    usage_bumps: list[UsageBump] | None = None,
    depth_chart_snapshot: Snapshot | None = None,
    star_players: StarPlayersResult | None = None,
    contest_teams: set[str] | None = None,
) -> GamePreviewResult:
    """One GamePreviewGame per this WEEK's own Schedule matchup (not
    week - 1 -- Vegas/Weather/Team Factors are all forward-looking context
    for the game about to be played). Empty `games` if the Schedule file
    hasn't been uploaded yet (schedule_rows == []), same as build_game_
    options' own empty-schedule case.

    The DST/Off Trends piece is the one exception to "this week's own
    data": it reviews the trailing window through week - 1 (see
    build_dst_trend_leaderboards), since a team's recent forcing/allowing
    form is what's relevant heading into this week's matchup, not
    something that exists for the week not yet played.

    The four Phase B params (tracker_rows/stat_lines_by_position/
    ownership_players/usage_bumps) all default to None -- omitting them
    entirely (Phase-A-only callers/tests) simply means every
    GamePreviewTeamSide.players list comes back empty, per
    build_team_player_tags' own "no signal, no row" behavior on an empty
    input set.

    The two Phase D params (depth_chart_snapshot/star_players) also
    default to None/empty -- omitting depth_chart_snapshot means every
    GamePreviewPlayer.depth comes back None and every
    GamePreviewTeamSide.injury_groups comes back empty (there's no
    injury-status data to summarize without a snapshot at all); omitting
    star_players just means no entry ever comes back with `starred=True`,
    same graceful-degradation convention as everywhere else.

    `contest_teams` (optional) narrows the full Schedule-file slate down to
    just the games on the currently-selected Contest's own DK salary slate
    -- same "a game is kept only if BOTH its teams are in that set"
    convention as build_game_options' own contest_teams (see that
    function's docstring for the full reasoning); left at its default
    (None) skips this filter entirely and every league-wide game still
    shows."""
    tracker_rows = tracker_rows or []
    stat_lines_by_position = stat_lines_by_position or {}
    ownership_players = ownership_players or []
    usage_bumps = usage_bumps or []
    star_players = star_players or StarPlayersResult()

    dst_result = build_dst_trend_leaderboards(dst_stat_lines, season, week, window_weeks)
    forcing_by_team = {r.team: r for r in dst_result.forcing}
    allowing_by_team = {r.team: r for r in dst_result.allowing}

    # Team pace trend + the new positional-matchup signal (see
    # game_preview_matchups.py's own module docstring) -- both computed
    # once up front, same "compute once, reuse per side" pattern as
    # dst_result above, rather than recomputing per team inside the loop.
    exploitable_positions_by_team = build_positional_matchup_signals(tracker_rows, schedule_rows, week, window_weeks)

    # One (team, player name) -> 1-indexed depth-chart rank lookup, built
    # once up front from the whole snapshot -- feeds both GamePreviewPlayer.
    # depth (Phase B's own player list) and, separately, build_team_
    # injury_groups (which re-walks the same snapshot for its own status/
    # grouping needs). Empty when no snapshot was supplied at all.
    depth_by_team_name: dict[tuple[str, str], int] = {}
    if depth_chart_snapshot is not None:
        for team_row in depth_chart_snapshot.teams:
            if team_row.team_abbrev is None:
                continue
            for players in team_row.positions.values():
                for depth, p in enumerate(players, start=1):
                    depth_by_team_name[(team_row.team_abbrev, p.player)] = depth

    # Phase C ownership bands (see game_preview_matchups.py's
    # compute_ownership_bands/classify_by_bands) need every game's
    # own numbers up front to rank against -- so this first pass builds
    # every side/game's own fields (everything EXCEPT narrative_sections,
    # which needs the band-derived Low/High Own flags as an input) and
    # collects the raw team/combined ownership values as it goes; a second
    # pass below then classifies each one against those bands and
    # builds the final GamePreviewGame list, narrative included.
    pre_games: list[dict] = []
    all_team_ownership_pcts: list[float] = []
    all_combined_ownership_pcts: list[float] = []
    for teams_set in games_for_week(schedule_rows, week):
        if contest_teams is not None and not teams_set <= contest_teams:
            continue
        teams = sorted(teams_set)
        schedule_entry = opponent_and_location(schedule_rows, teams[0], week)
        if schedule_entry is None:
            continue
        resolved = resolve_away_home(teams[0], schedule_entry[0], schedule_entry[1] == "Home")
        if resolved is None:
            continue
        away_team, home_team = resolved
        key = game_key(away_team, home_team)
        label = game_label(away_team, home_team)
        vegas_for_game = _vegas_for_game(vegas, key)
        weather_for_game = _weather_for_game(weather, key)

        away_side = GamePreviewTeamSide(
            team=away_team,
            is_home=False,
            team_factors=_team_factors(away_team, factors_by_team_position),
            dst_matchup=_dst_matchup(away_team, home_team, forcing_by_team, allowing_by_team),
            pace_trend=build_team_pace_trend(away_team, week, stat_lines_by_position),
            exploitable_positions=exploitable_positions_by_team.get(away_team, []),
            projected_ownership_pct=team_projected_ownership_pct(away_team, ownership_players),
            players=build_team_player_tags(
                away_team,
                tracker_rows,
                schedule_rows,
                week,
                window_weeks,
                stat_lines_by_position,
                ownership_players,
                usage_bumps,
                depth_by_name={name: d for (t, name), d in depth_by_team_name.items() if t == away_team},
                opponent=home_team,
                opponent_exploitable_positions=exploitable_positions_by_team.get(home_team, []),
            ),
            injury_groups=(
                build_team_injury_groups(away_team, depth_chart_snapshot, star_players)
                if depth_chart_snapshot is not None
                else []
            ),
        )
        home_side = GamePreviewTeamSide(
            team=home_team,
            is_home=True,
            team_factors=_team_factors(home_team, factors_by_team_position),
            dst_matchup=_dst_matchup(home_team, away_team, forcing_by_team, allowing_by_team),
            pace_trend=build_team_pace_trend(home_team, week, stat_lines_by_position),
            exploitable_positions=exploitable_positions_by_team.get(home_team, []),
            projected_ownership_pct=team_projected_ownership_pct(home_team, ownership_players),
            players=build_team_player_tags(
                home_team,
                tracker_rows,
                schedule_rows,
                week,
                window_weeks,
                stat_lines_by_position,
                ownership_players,
                usage_bumps,
                depth_by_name={name: d for (t, name), d in depth_by_team_name.items() if t == home_team},
                opponent=away_team,
                opponent_exploitable_positions=exploitable_positions_by_team.get(away_team, []),
            ),
            injury_groups=(
                build_team_injury_groups(home_team, depth_chart_snapshot, star_players)
                if depth_chart_snapshot is not None
                else []
            ),
        )

        combined_ownership = _combined_projected_ownership_pct(
            away_side.projected_ownership_pct, home_side.projected_ownership_pct
        )
        over_under = vegas_for_game.over_under if vegas_for_game is not None else None
        ratio = _total_to_ownership_ratio(combined_ownership, over_under)
        high_over_under = is_high_over_under(over_under)
        low_over_under = is_low_over_under(over_under)

        if away_side.projected_ownership_pct is not None:
            all_team_ownership_pcts.append(away_side.projected_ownership_pct)
        if home_side.projected_ownership_pct is not None:
            all_team_ownership_pcts.append(home_side.projected_ownership_pct)
        if combined_ownership is not None:
            all_combined_ownership_pcts.append(combined_ownership)

        pre_games.append(
            {
                "key": key,
                "label": label,
                "away_team": away_team,
                "home_team": home_team,
                "vegas_for_game": vegas_for_game,
                "weather_for_game": weather_for_game,
                "away_side": away_side,
                "home_side": home_side,
                "combined_ownership": combined_ownership,
                "over_under": over_under,
                "ratio": ratio,
                "high_over_under": high_over_under,
                "low_over_under": low_over_under,
            }
        )

    # Second pass -- now that every game's own team/combined ownership
    # numbers are in hand, rank them against each other (see
    # game_preview_matchups.py's compute_ownership_bands' own
    # docstring for why this needs the whole week's population, not just
    # one game at a time) and build the final GamePreviewGame list,
    # narrative included.
    team_bands = compute_ownership_bands(all_team_ownership_pcts)
    combined_bands = compute_ownership_bands(all_combined_ownership_pcts)

    games: list[GamePreviewGame] = []
    for pre in pre_games:
        away_side = pre["away_side"]
        home_side = pre["home_side"]
        away_ownership_flag = classify_by_bands(away_side.projected_ownership_pct, team_bands)
        home_ownership_flag = classify_by_bands(home_side.projected_ownership_pct, team_bands)
        combined_ownership_flag = classify_by_bands(pre["combined_ownership"], combined_bands)

        games.append(
            GamePreviewGame(
                key=pre["key"],
                label=pre["label"],
                teams=[pre["away_team"], pre["home_team"]],
                vegas=pre["vegas_for_game"],
                weather=pre["weather_for_game"],
                away=away_side,
                home=home_side,
                narrative_sections=build_game_narrative(
                    pre["label"],
                    away_side,
                    home_side,
                    pre["vegas_for_game"],
                    pre["combined_ownership"],
                    pre["ratio"],
                    pre["high_over_under"],
                    pre["low_over_under"],
                    away_ownership_flag=away_ownership_flag,
                    home_ownership_flag=home_ownership_flag,
                    combined_ownership_flag=combined_ownership_flag,
                ),
                combined_projected_ownership_pct=pre["combined_ownership"],
                total_to_ownership_ratio=pre["ratio"],
                high_over_under=pre["high_over_under"],
                low_over_under=pre["low_over_under"],
            )
        )

    games.sort(key=lambda g: g.label)
    return GamePreviewResult(
        season=season,
        week=week,
        through_week=dst_result.through_week,
        window_weeks=window_weeks,
        games=games,
    )
