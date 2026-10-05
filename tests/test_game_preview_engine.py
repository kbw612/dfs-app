from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.team_factors.team_factors import TeamFactorEntry
from backend.schemas.vegas_lines.vegas_lines import VegasLineGame, VegasLinesSnapshot, VegasLineValues
from backend.schemas.weather.weather import WeatherGame, WeatherSnapshot
from backend.services.game_preview.game_preview_engine import _combined_tier, build_game_preview
from backend.services.schedule.schedule_loader import parse_schedule_csv


def _ownership_player(player, position, team, ownership_pct):
    return OwnershipPlayer(
        player=player,
        position=position,
        team=team,
        opponent="OPP",
        salary=6000,
        ownership_pct=ownership_pct,
    )

SCHEDULE_CSV = (
    "Team,Week,Opponent,GameLocation\n"
    "LAC,3,DEN,Away\n"
    "DEN,3,LAC,Home\n"
    "KC,3,BYE,BYE\n"
)


def _schedule_rows():
    return parse_schedule_csv(SCHEDULE_CSV)


def _dst_line(team, opponent, week, sacks, def_int=0, fumble_recoveries=0):
    return {
        "team": team,
        "opponent": opponent,
        "sacks": sacks,
        "def_int": def_int,
        "fumble_recoveries": fumble_recoveries,
    }


def test_build_game_preview_lists_this_weeks_games_skipping_byes():
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, None, {})
    assert [g.label for g in result.games] == ["LAC @ DEN"]


def test_build_game_preview_resolves_away_home_sides():
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, None, {})
    game = result.games[0]
    assert game.away.team == "LAC"
    assert game.away.is_home is False
    assert game.home.team == "DEN"
    assert game.home.is_home is True


def test_build_game_preview_vegas_lookup_by_game_key():
    vegas = VegasLinesSnapshot(
        season=2026,
        week=3,
        initial_scraped_at="2026-09-01T00:00:00",
        current_scraped_at="2026-09-05T00:00:00",
        games=[
            VegasLineGame(
                away_name="Chargers",
                home_name="Broncos",
                away_team="LAC",
                home_team="DEN",
                game_key="DEN-LAC",
                kickoff_label="Sunday 4:25pm",
                initial=VegasLineValues(over_under=44.0, home_implied_total=24.0, away_implied_total=20.0),
                current=VegasLineValues(over_under=45.5, home_implied_total=23.0, away_implied_total=22.5),
            )
        ],
    )
    result = build_game_preview(2026, 3, _schedule_rows(), {}, vegas, None, {})
    v = result.games[0].vegas
    assert v is not None
    assert v.over_under == 45.5
    assert v.home_implied_total == 23.0
    assert v.away_implied_total == 22.5
    assert v.kickoff_label == "Sunday 4:25pm"


def test_build_game_preview_vegas_none_when_no_matching_game():
    vegas = VegasLinesSnapshot(
        season=2026, week=3, initial_scraped_at="x", current_scraped_at="x", games=[]
    )
    result = build_game_preview(2026, 3, _schedule_rows(), {}, vegas, None, {})
    assert result.games[0].vegas is None


def test_build_game_preview_weather_lookup_by_game_key():
    weather = WeatherSnapshot(
        season=2026,
        week=3,
        scraped_at="2026-09-05T00:00:00",
        games=[
            WeatherGame(
                away_name="Los Angeles Chargers",
                home_name="Denver Broncos",
                away_team="LAC",
                home_team="DEN",
                game_key="DEN-LAC",
                kickoff_label="4:25 PM ET",
                color="yellow",
                note="Winds gusting to 20mph",
            )
        ],
    )
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, weather, {})
    w = result.games[0].weather
    assert w is not None
    assert w.color == "yellow"
    assert w.note == "Winds gusting to 20mph"


def test_build_game_preview_dst_matchup_joins_forcing_and_allowing():
    dst_stat_lines = {
        # LAC forcing: 4 + 2 = 6 sacks over 2 games -> 3.0/g.
        ("Chargers", 1): _dst_line("LAC", "MIA", 1, sacks=4),
        ("Chargers", 2): _dst_line("LAC", "KC", 2, sacks=2),
        # DEN forcing: 2 + 2 = 4 sacks over 2 games -> 2.0/g.
        ("Broncos", 1): _dst_line("DEN", "TEN", 1, sacks=2),
        ("Broncos", 2): _dst_line("DEN", "NYJ", 2, sacks=2),
        # LAC allowing (some other team's DST naming LAC as opponent):
        # 1 + 3 = 4 sacks over 2 games -> 2.0/g.
        ("Dolphins", 1): _dst_line("MIA", "LAC", 1, sacks=1),
        ("Chiefs", 2): _dst_line("KC", "LAC", 2, sacks=3),
        # DEN allowing: 2 + 2 = 4 sacks over 2 games -> 2.0/g.
        ("Titans", 1): _dst_line("TEN", "DEN", 1, sacks=2),
        ("Jets", 2): _dst_line("NYJ", "DEN", 2, sacks=2),
    }
    result = build_game_preview(2026, 3, _schedule_rows(), dst_stat_lines, None, None, {})
    game = result.games[0]
    lac_matchup = game.away.dst_matchup
    assert lac_matchup is not None
    assert lac_matchup.sacks_per_game_forced == 3.0
    assert lac_matchup.opponent_sacks_per_game_allowed == 2.0

    den_matchup = game.home.dst_matchup
    assert den_matchup is not None
    assert den_matchup.sacks_per_game_forced == 2.0
    assert den_matchup.opponent_sacks_per_game_allowed == 2.0


def test_build_game_preview_dst_matchup_none_when_week_is_1():
    schedule_rows = parse_schedule_csv(SCHEDULE_CSV + "LAC,1,DEN,Away\nDEN,1,LAC,Home\n")
    result = build_game_preview(2026, 1, schedule_rows, {}, None, None, {})
    # week 1 has no prior week to review -- through_week is 0, so no team
    # has a forcing/allowing row at all yet.
    assert result.through_week == 0
    game = next(g for g in result.games if g.label == "LAC @ DEN")
    assert game.away.dst_matchup is None
    assert game.home.dst_matchup is None


def test_build_game_preview_team_factors_populated_per_position():
    factors = {
        ("LAC", "WR"): TeamFactorEntry(season=2026, team="LAC", position="WR", factor=2.75),
        ("LAC", "DST"): TeamFactorEntry(season=2026, team="LAC", position="DST", factor=1.5),
    }
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, None, factors)
    away_factors = result.games[0].away.team_factors
    assert away_factors.wr == 2.75
    assert away_factors.dst == 1.5
    # Never explicitly set -- comes back None, not a fabricated default.
    assert away_factors.qb is None
    assert away_factors.rb is None
    assert away_factors.te is None


def test_build_game_preview_empty_schedule_gives_no_games():
    result = build_game_preview(2026, 3, [], {}, None, None, {})
    assert result.games == []


def test_build_game_preview_through_week_and_window_weeks_on_result():
    result = build_game_preview(2026, 4, _schedule_rows(), {}, None, None, {}, window_weeks=3)
    assert result.through_week == 3
    assert result.window_weeks == 3


def test_build_game_preview_contest_teams_filters_to_both_sides_present():
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, None, {}, contest_teams={"LAC", "DEN"})
    assert [g.label for g in result.games] == ["LAC @ DEN"]


def test_build_game_preview_contest_teams_excludes_game_missing_a_side():
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, None, {}, contest_teams={"LAC"})
    assert result.games == []


def test_build_game_preview_contest_teams_none_skips_filter():
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, None, {}, contest_teams=None)
    assert [g.label for g in result.games] == ["LAC @ DEN"]


def _tracker_row(name, position, team, week, salary=6000, fpts=10.0):
    return DkPlayerRow(
        name=name,
        position=position,
        roster_position=position,
        team=team,
        week=week,
        salary=salary,
        pct_drafted=10.0,
        fpts=fpts,
        non_td_fpts=fpts,
        td_fpts=0.0,
    )


def test_build_game_preview_pace_trend_populated_per_side():
    stat_lines_by_position = {
        "QB": {("LAC QB", 2): {"team": "LAC", "pass_att": 30}},
        "RB": {("LAC RB", 2): {"team": "LAC", "rush_att": 20}},
    }
    result = build_game_preview(
        2026, 3, _schedule_rows(), {}, None, None, {}, stat_lines_by_position=stat_lines_by_position
    )
    away_pace = result.games[0].away.pace_trend
    assert away_pace is not None
    assert away_pace.week == 2
    assert away_pace.plays == 50
    # DEN has no stat lines at all -- pace_trend stays None, same
    # graceful-degradation convention as every other optional field.
    assert result.games[0].home.pace_trend is None


def test_build_game_preview_exploitable_positions_and_tag_flow_to_opponent():
    # DEN has allowed elevated WR production (vs. a league baseline from
    # KC/MIA facing each other, outside DEN's own window) across two
    # multiplier-clearing games in the trailing window -- LAC's own WR
    # should then pick up a "play" tag referencing DEN's own matchup.
    tracker_rows = [
        _tracker_row("Opp WR 1", "WR", "MIA", 2, salary=6000, fpts=30.0),  # vs DEN, week 2
        _tracker_row("Opp WR 2", "WR", "MIA", 1, salary=6000, fpts=25.0),  # vs DEN, week 1
        _tracker_row("Baseline WR", "WR", "KC", 1, salary=6000, fpts=8.0),  # vs MIA, no DEN involvement
        _tracker_row("LAC WR", "WR", "LAC", 2, salary=6000, fpts=12.0),
    ]
    schedule_rows = parse_schedule_csv(
        SCHEDULE_CSV
        + "MIA,2,DEN,Home\nDEN,2,MIA,Away\n"
        + "MIA,1,DEN,Away\nDEN,1,MIA,Home\n"
        + "KC,1,MIA,Away\n"
    )
    result = build_game_preview(
        2026,
        3,
        schedule_rows,
        {},
        None,
        None,
        {},
        tracker_rows=tracker_rows,
        stat_lines_by_position={},
        window_weeks=5,
    )
    game = next(g for g in result.games if g.label == "LAC @ DEN")
    assert any(s.position == "WR" for s in game.home.exploitable_positions)
    lac_wr = next(p for p in game.away.players if p.name == "LAC WR")
    assert any("DEN has allowed" in t.reason for t in lac_wr.tags)


def test_build_game_preview_computes_ownership_ratio_and_high_over_under():
    ownership_players = [
        _ownership_player("LAC QB1", "QB", "LAC", 40.0),
        _ownership_player("LAC RB1", "RB", "LAC", 20.0),
        _ownership_player("DEN QB1", "QB", "DEN", 50.0),
    ]
    vegas = VegasLinesSnapshot(
        season=2026,
        week=3,
        initial_scraped_at="x",
        current_scraped_at="x",
        games=[
            VegasLineGame(
                away_name="Chargers",
                home_name="Broncos",
                away_team="LAC",
                home_team="DEN",
                game_key="DEN-LAC",
                initial=VegasLineValues(over_under=44.0),
                current=VegasLineValues(over_under=51.5),
            )
        ],
    )
    result = build_game_preview(2026, 3, _schedule_rows(), {}, vegas, None, {}, ownership_players=ownership_players)
    game = result.games[0]
    assert game.away.projected_ownership_pct == 60.0
    assert game.home.projected_ownership_pct == 50.0
    assert game.combined_projected_ownership_pct == 110.0
    assert game.total_to_ownership_ratio == round(110.0 / 51.5, 2)
    assert game.high_over_under is True
    assert game.low_over_under is False
    ownership_section = next(s for s in game.narrative_sections if s.label == "Ownership")
    assert any(e.startswith("Game Total-to-Ownership Ratio") for e in ownership_section.entries)
    assert any("high-total game" in e for e in ownership_section.entries)


def test_build_game_preview_computes_low_over_under():
    ownership_players = [
        _ownership_player("LAC QB1", "QB", "LAC", 20.0),
        _ownership_player("DEN QB1", "QB", "DEN", 15.0),
    ]
    vegas = VegasLinesSnapshot(
        season=2026,
        week=3,
        initial_scraped_at="x",
        current_scraped_at="x",
        games=[
            VegasLineGame(
                away_name="Chargers",
                home_name="Broncos",
                away_team="LAC",
                home_team="DEN",
                game_key="DEN-LAC",
                initial=VegasLineValues(over_under=44.0),
                current=VegasLineValues(over_under=38.0),
            )
        ],
    )
    result = build_game_preview(2026, 3, _schedule_rows(), {}, vegas, None, {}, ownership_players=ownership_players)
    game = result.games[0]
    assert game.low_over_under is True
    assert game.high_over_under is False
    ownership_section = next(s for s in game.narrative_sections if s.label == "Ownership")
    assert any("low-total game" in e for e in ownership_section.entries)


def test_build_game_preview_projected_ownership_none_without_ownership_data():
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, None, {})
    game = result.games[0]
    assert game.away.projected_ownership_pct is None
    assert game.home.projected_ownership_pct is None
    assert game.combined_projected_ownership_pct is None
    assert game.total_to_ownership_ratio is None
    assert game.high_over_under is False
    assert game.low_over_under is False


def test_build_game_preview_flags_ownership_by_week_bands():
    # Eight teams across four games -- enough for compute_ownership_bands'
    # own MIN_BAND_SAMPLE_SIZE (4) to kick in for both the per-team (8
    # values) and whole-game (4 values) rankings. Team pcts
    # [5, 10, 15, 20, 60, 65, 90, 95] give a 33rd/67th percentile of
    # 16.67/63.33 (verified via statistics.quantiles), so 5/10/15 flag low
    # and 65/90/95 flag high (20/60 stay neutral); combined pcts
    # [100, 100, 80, 80] give 80.0/100.0, so the two 80-combined games flag
    # low and the two 100-combined games flag high.
    schedule_csv = (
        "Team,Week,Opponent,GameLocation\n"
        "TMA,3,TMB,Away\n"
        "TMB,3,TMA,Home\n"
        "TMC,3,TMD,Away\n"
        "TMD,3,TMC,Home\n"
        "TME,3,TMF,Away\n"
        "TMF,3,TME,Home\n"
        "TMG,3,TMH,Away\n"
        "TMH,3,TMG,Home\n"
    )
    schedule_rows = parse_schedule_csv(schedule_csv)
    ownership_players = [
        _ownership_player("TMA QB1", "QB", "TMA", 5.0),
        _ownership_player("TMB QB1", "QB", "TMB", 95.0),
        _ownership_player("TMC QB1", "QB", "TMC", 10.0),
        _ownership_player("TMD QB1", "QB", "TMD", 90.0),
        _ownership_player("TME QB1", "QB", "TME", 15.0),
        _ownership_player("TMF QB1", "QB", "TMF", 65.0),
        _ownership_player("TMG QB1", "QB", "TMG", 20.0),
        _ownership_player("TMH QB1", "QB", "TMH", 60.0),
    ]
    result = build_game_preview(2026, 3, schedule_rows, {}, None, None, {}, ownership_players=ownership_players)
    games_by_label = {g.label: g for g in result.games}

    def _combined_line(game):
        section = next(s for s in game.narrative_sections if s.label == "Ownership")
        return next(e for e in section.entries if "projected ownership" in e)

    # TMA (5.0, low) @ TMB (95.0, high); combined 100.0 -> also flagged high.
    assert _combined_line(games_by_label["TMA @ TMB"]) == (
        "\U0001f4c8 100.0% projected ownership = \U0001f4c9 TMA 5.0% + \U0001f4c8 TMB 95.0%"
    )
    # TME (15.0, low) @ TMF (65.0, high); combined 80.0 -> flagged low.
    assert _combined_line(games_by_label["TME @ TMF"]) == (
        "\U0001f4c9 80.0% projected ownership = \U0001f4c9 TME 15.0% + \U0001f4c8 TMF 65.0%"
    )


def test_combined_tier_high_wins_over_low():
    # An unusual combination (high on one sub-stat, low on the other) --
    # "high" wins so the pair reads as elevated overall rather than
    # suppressed.
    assert _combined_tier("high", "low") == "high"
    assert _combined_tier("low", "high") == "high"


def test_combined_tier_low_when_either_low_and_neither_high():
    assert _combined_tier("low", None) == "low"
    assert _combined_tier(None, "low") == "low"


def test_combined_tier_none_when_neither_set():
    assert _combined_tier(None, None) is None


def test_combined_tier_handles_more_than_two_reads():
    # _volume_tier_flags feeds in average_tier AND median_tier for both
    # sub-stats at once (four reads per call) -- any single "high" among
    # them should still win, same as the two-arg case above.
    assert _combined_tier(None, None, None, "high") == "high"
    assert _combined_tier(None, "low", None, None) == "low"
    assert _combined_tier(None, None, None, None) is None


def test_build_game_preview_stat_summary_none_without_tracker_data():
    # Neither tracker_rows nor stat_lines_by_position supplied -- same
    # graceful-degradation convention as pace_trend being None.
    result = build_game_preview(2026, 3, _schedule_rows(), {}, None, None, {})
    game = result.games[0]
    assert game.away.stat_summary is None
    assert game.away.run_volume_tier is None
    assert game.away.pass_volume_tier is None
    assert game.home.stat_summary is None
    assert game.home.run_volume_tier is None
    assert game.home.pass_volume_tier is None


def test_build_game_preview_stat_summary_run_high_pass_low():
    # LAC: Rush Att 35 (>=30 high), Rush Yds 160 (>=141 high), Pass Att 20
    # (<=28 low), Pass Yds 100 (<=175 low) -- rush elevated, pass
    # suppressed -- run_volume_tier "high", pass_volume_tier "low".
    tracker_rows = [
        _tracker_row("LAC QB1", "QB", "LAC", 2, fpts=20.0),
        _tracker_row("LAC RB1", "RB", "LAC", 2, fpts=15.0),
    ]
    stat_lines_by_position = {
        "QB": {("LAC QB1", 2): {"pass_att": 20, "pass_yds": 100}},
        "RB": {("LAC RB1", 2): {"rush_att": 35, "rush_yards": 160}},
    }
    result = build_game_preview(
        2026,
        3,
        _schedule_rows(),
        {},
        None,
        None,
        {},
        tracker_rows=tracker_rows,
        stat_lines_by_position=stat_lines_by_position,
    )
    game = result.games[0]
    away = game.away
    assert away.team == "LAC"
    assert away.stat_summary is not None
    assert away.stat_summary.rush_att.average == 35.0
    assert away.stat_summary.rush_att.average_tier == "high"
    assert away.stat_summary.rush_yards.average_tier == "high"
    assert away.stat_summary.pass_att.average_tier == "low"
    assert away.stat_summary.pass_yds.average_tier == "low"
    assert away.run_volume_tier == "high"
    assert away.pass_volume_tier == "low"
    # DEN has no stat lines at all this window.
    assert game.home.stat_summary is None
    assert game.home.run_volume_tier is None
    assert game.home.pass_volume_tier is None


def test_build_game_preview_stat_summary_pass_high_run_low():
    # LAC: Pass Att 45 (>=38 high), Pass Yds 300 (>=261 high), Rush Att 10
    # (<=21 low), Rush Yds 40 (<=85 low) -- pass elevated, rush
    # suppressed -- pass_volume_tier "high", run_volume_tier "low".
    tracker_rows = [
        _tracker_row("LAC QB1", "QB", "LAC", 2, fpts=20.0),
        _tracker_row("LAC RB1", "RB", "LAC", 2, fpts=15.0),
    ]
    stat_lines_by_position = {
        "QB": {("LAC QB1", 2): {"pass_att": 45, "pass_yds": 300}},
        "RB": {("LAC RB1", 2): {"rush_att": 10, "rush_yards": 40}},
    }
    result = build_game_preview(
        2026,
        3,
        _schedule_rows(),
        {},
        None,
        None,
        {},
        tracker_rows=tracker_rows,
        stat_lines_by_position=stat_lines_by_position,
    )
    away = result.games[0].away
    assert away.pass_volume_tier == "high"
    assert away.run_volume_tier == "low"


def test_build_game_preview_stat_summary_both_high_when_both_sides_elevated():
    # Both Rush Att (35, high) and Pass Att (45, high) elevated at once --
    # the two tiers are independent, so both come back "high" together
    # (this is the whole point of splitting the old single "lean" pick
    # into two separate fields -- a team can be both at once).
    tracker_rows = [
        _tracker_row("LAC QB1", "QB", "LAC", 2, fpts=20.0),
        _tracker_row("LAC RB1", "RB", "LAC", 2, fpts=15.0),
    ]
    stat_lines_by_position = {
        "QB": {("LAC QB1", 2): {"pass_att": 45, "pass_yds": 300}},
        "RB": {("LAC RB1", 2): {"rush_att": 35, "rush_yards": 160}},
    }
    result = build_game_preview(
        2026,
        3,
        _schedule_rows(),
        {},
        None,
        None,
        {},
        tracker_rows=tracker_rows,
        stat_lines_by_position=stat_lines_by_position,
    )
    away = result.games[0].away
    assert away.run_volume_tier == "high"
    assert away.pass_volume_tier == "high"


def test_build_game_preview_stat_summary_both_low_when_both_sides_suppressed():
    # Both Rush Att (10, low) and Pass Att (20, low) suppressed at once --
    # independent fields, so both come back "low" together.
    tracker_rows = [
        _tracker_row("LAC QB1", "QB", "LAC", 2, fpts=20.0),
        _tracker_row("LAC RB1", "RB", "LAC", 2, fpts=15.0),
    ]
    stat_lines_by_position = {
        "QB": {("LAC QB1", 2): {"pass_att": 20, "pass_yds": 100}},
        "RB": {("LAC RB1", 2): {"rush_att": 10, "rush_yards": 40}},
    }
    result = build_game_preview(
        2026,
        3,
        _schedule_rows(),
        {},
        None,
        None,
        {},
        tracker_rows=tracker_rows,
        stat_lines_by_position=stat_lines_by_position,
    )
    away = result.games[0].away
    assert away.run_volume_tier == "low"
    assert away.pass_volume_tier == "low"


def test_build_game_preview_stat_summary_both_none_when_neither_elevated():
    # Rush Att 25 and Pass Att 32 both sit strictly between their own
    # low/high thresholds -- neither tier should be set, even though
    # stat_summary itself is present (distinguishing "genuinely normal"
    # from "no data at all" is the caller's job -- see
    # GamePreviewTeamSide.run_volume_tier's own docstring).
    tracker_rows = [
        _tracker_row("LAC QB1", "QB", "LAC", 2, fpts=20.0),
        _tracker_row("LAC RB1", "RB", "LAC", 2, fpts=15.0),
    ]
    stat_lines_by_position = {
        "QB": {("LAC QB1", 2): {"pass_att": 32, "pass_yds": 220}},
        "RB": {("LAC RB1", 2): {"rush_att": 25, "rush_yards": 110}},
    }
    result = build_game_preview(
        2026,
        3,
        _schedule_rows(),
        {},
        None,
        None,
        {},
        tracker_rows=tracker_rows,
        stat_lines_by_position=stat_lines_by_position,
    )
    away = result.games[0].away
    assert away.stat_summary is not None
    assert away.run_volume_tier is None
    assert away.pass_volume_tier is None


def test_build_game_preview_stat_summary_includes_td_stats():
    tracker_rows = [_tracker_row("LAC RB1", "RB", "LAC", 2, fpts=15.0)]
    stat_lines_by_position = {"RB": {("LAC RB1", 2): {"rush_att": 20, "rush_yards": 90, "rush_td": 2}}}
    result = build_game_preview(
        2026,
        3,
        _schedule_rows(),
        {},
        None,
        None,
        {},
        tracker_rows=tracker_rows,
        stat_lines_by_position=stat_lines_by_position,
    )
    away = result.games[0].away
    assert away.stat_summary is not None
    assert away.stat_summary.rush_td.average == 2.0
    # TD stats have no defined thresholds -- always untiered.
    assert away.stat_summary.rush_td.average_tier is None
    assert away.stat_summary.rush_td.median_tier is None
