from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.game_preview.game_preview_matchups import (
    build_positional_matchup_signals,
    build_team_pace_trend,
    classify_by_bands,
    combined_projected_ownership_pct,
    compute_ownership_bands,
    is_high_over_under,
    is_low_over_under,
    team_projected_ownership_pct,
    total_to_ownership_ratio,
)
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
    "LAC,10,DEN,Away\n"
    "DEN,10,LAC,Home\n"
    "LAC,9,KC,Home\n"
    "KC,9,LAC,Away\n"
    "LAC,8,MIA,Away\n"
    "MIA,8,LAC,Home\n"
    "DEN,9,MIA,Away\n"
    "MIA,9,DEN,Home\n"
    "DEN,8,KC,Home\n"
    "KC,8,DEN,Away\n"
)


def _schedule_rows():
    return parse_schedule_csv(SCHEDULE_CSV)


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


# -- build_positional_matchup_signals --


def test_positional_matchup_fires_when_both_fpts_and_multiplier_clear_bar():
    tracker_rows = [
        # DEN's own opponents (LAC week 10, MIA week 9) both torch DEN's
        # WRs at a high multiplier.
        _tracker_row("LAC WR1", "WR", "LAC", 10, salary=6000, fpts=30.0),  # vs DEN, 5.0x
        _tracker_row("MIA WR1", "WR", "MIA", 9, salary=6000, fpts=25.0),  # vs DEN, 4.17x
        # A league-wide baseline of low-scoring WR games against a team
        # NOT in DEN's own window (KC vs LAC week 9, MIA vs LAC week 8),
        # so DEN's allowed average is clearly above league average without
        # also inflating DEN's own bucket.
        _tracker_row("KC WR1", "WR", "KC", 9, salary=6000, fpts=8.0),  # vs LAC
        _tracker_row("MIA WR1", "WR", "MIA", 8, salary=6000, fpts=8.0),  # vs LAC
    ]
    signals = build_positional_matchup_signals(tracker_rows, _schedule_rows(), 11, 5)
    assert "DEN" in signals
    wr_signal = next(s for s in signals["DEN"] if s.position == "WR")
    assert wr_signal.games == 2
    assert wr_signal.high_multiplier_games == 2
    assert wr_signal.avg_fpts_allowed > wr_signal.league_avg_fpts


def test_positional_matchup_does_not_fire_with_only_one_game():
    tracker_rows = [
        _tracker_row("LAC WR1", "WR", "LAC", 10, salary=6000, fpts=30.0),  # vs DEN, only 1 game
        _tracker_row("KC WR1", "WR", "KC", 9, salary=6000, fpts=8.0),
    ]
    signals = build_positional_matchup_signals(tracker_rows, _schedule_rows(), 11, 5)
    assert "DEN" not in signals


def test_positional_matchup_does_not_fire_when_fpts_not_above_average():
    # Both DEN's own games and the league baseline score the same -- no
    # real above-average signal even though the multiplier bar is cleared.
    tracker_rows = [
        _tracker_row("LAC WR1", "WR", "LAC", 10, salary=6000, fpts=20.0),
        _tracker_row("MIA WR1", "WR", "MIA", 9, salary=6000, fpts=20.0),
        _tracker_row("KC WR1", "WR", "KC", 9, salary=6000, fpts=20.0),
        _tracker_row("MIA WR1", "WR", "MIA", 8, salary=6000, fpts=20.0),
    ]
    signals = build_positional_matchup_signals(tracker_rows, _schedule_rows(), 11, 5)
    assert "DEN" not in signals


def test_positional_matchup_does_not_fire_when_multiplier_bar_not_cleared():
    # High FPTS allowed, but salaries are high enough that neither game
    # clears the high-multiplier threshold.
    tracker_rows = [
        _tracker_row("LAC WR1", "WR", "LAC", 10, salary=9000, fpts=30.0),  # 3.33x
        _tracker_row("MIA WR1", "WR", "MIA", 9, salary=9000, fpts=25.0),  # 2.78x
        _tracker_row("KC WR1", "WR", "KC", 9, salary=6000, fpts=8.0),
        _tracker_row("MIA WR1", "WR", "MIA", 8, salary=6000, fpts=8.0),
    ]
    signals = build_positional_matchup_signals(tracker_rows, _schedule_rows(), 11, 5)
    assert "DEN" not in signals


def test_positional_matchup_counts_real_games_not_player_rows():
    # Two RBs both play for LAC against DEN in the SAME week -- this must
    # count as ONE game, not two, and ONE high-multiplier game (not two)
    # even though both individual rows clear the multiplier bar. Regression
    # test for the bug where a single game with 2 hot RBs was reported as
    # "2 high-multiplier games."
    tracker_rows = [
        _tracker_row("LAC RB1", "RB", "LAC", 10, salary=6000, fpts=30.0),  # vs DEN, 5.0x
        _tracker_row("LAC RB2", "RB", "LAC", 10, salary=6000, fpts=25.0),  # vs DEN, same game, 4.17x
        # A second real game against DEN, also hot, so the games count
        # should be 2 (not 3+) and high_multiplier_games should be 2 (one
        # per real game, not one per player-row).
        _tracker_row("MIA RB1", "RB", "MIA", 9, salary=6000, fpts=28.0),  # vs DEN, 4.67x
        # League baseline, unrelated to DEN.
        _tracker_row("KC RB1", "RB", "KC", 9, salary=6000, fpts=8.0),
        _tracker_row("MIA RB1", "RB", "MIA", 8, salary=6000, fpts=8.0),
    ]
    signals = build_positional_matchup_signals(tracker_rows, _schedule_rows(), 11, 5)
    rb_signal = next(s for s in signals["DEN"] if s.position == "RB")
    # 2 real games (week 10 and week 9), not 3 player-rows.
    assert rb_signal.games == 2
    # Combined FPTS for week 10's game is 30 + 25 = 55.
    assert rb_signal.avg_fpts_allowed == (55.0 + 28.0) / 2
    # 2 real high-multiplier GAMES, not 3 high-multiplier player-rows.
    assert rb_signal.high_multiplier_games == 2


def test_positional_matchup_requires_absolute_fpts_floor_not_just_ratio():
    # DEN allows RBs a small amount above the league average (7.1 vs a low
    # 3.6 average -- easily clears ABOVE_AVERAGE_FPTS_RATIO) but neither
    # number is anywhere near a real DFS-relevant total. This must NOT fire
    # even with 2+ high-multiplier games, since it fails the absolute
    # MIN_AVG_FPTS_ALLOWED_BY_POSITION floor.
    tracker_rows = [
        _tracker_row("LAC RB", "RB", "LAC", 10, salary=2000, fpts=7.0),  # vs DEN, 3.5x
        _tracker_row("MIA RB", "RB", "MIA", 9, salary=2000, fpts=7.5),  # vs DEN, 3.75x
        _tracker_row("KC RB", "RB", "KC", 9, salary=6000, fpts=3.5),
        _tracker_row("MIA RB", "RB", "MIA", 8, salary=6000, fpts=3.5),
    ]
    signals = build_positional_matchup_signals(tracker_rows, _schedule_rows(), 11, 5)
    assert "DEN" not in signals


def test_positional_matchup_dst_is_excluded():
    tracker_rows = [
        _tracker_row("LAC DST", "DST", "LAC", 10, salary=3000, fpts=20.0),
        _tracker_row("MIA DST", "DST", "MIA", 9, salary=3000, fpts=18.0),
    ]
    signals = build_positional_matchup_signals(tracker_rows, _schedule_rows(), 11, 5)
    assert signals == {}


def test_positional_matchup_skips_rows_outside_window():
    tracker_rows = [
        # Week 3 is outside a [6, 11) window.
        _tracker_row("LAC WR1", "WR", "LAC", 3, salary=6000, fpts=30.0),
    ]
    signals = build_positional_matchup_signals(tracker_rows, _schedule_rows(), 11, 5)
    assert signals == {}


# -- build_team_pace_trend --


def test_pace_trend_none_when_no_played_week():
    result = build_team_pace_trend("LAC", 1, {})
    assert result is None


def test_pace_trend_computes_plays_and_pass_rate_for_most_recent_week():
    stat_lines_by_position = {
        "QB": {("LAC QB", 10): {"team": "LAC", "pass_att": 30}},
        "RB": {("LAC RB", 10): {"team": "LAC", "rush_att": 20}},
    }
    result = build_team_pace_trend("LAC", 11, stat_lines_by_position)
    assert result is not None
    assert result.week == 10
    assert result.plays == 50
    assert result.pass_att == 30
    assert result.rush_att == 20
    assert result.pass_rate_pct == 60.0
    assert result.rush_rate_pct == 40.0
    # No prior played week in this fixture.
    assert result.plays_delta is None
    assert result.pass_rate_delta is None


def test_pace_trend_computes_deltas_against_prior_played_week():
    stat_lines_by_position = {
        "QB": {
            ("LAC QB", 10): {"team": "LAC", "pass_att": 30},
            ("LAC QB", 9): {"team": "LAC", "pass_att": 20},
        },
        "RB": {
            ("LAC RB", 10): {"team": "LAC", "rush_att": 20},
            ("LAC RB", 9): {"team": "LAC", "rush_att": 30},
        },
    }
    result = build_team_pace_trend("LAC", 11, stat_lines_by_position)
    assert result is not None
    assert result.week == 10
    assert result.plays == 50
    # Prior week: 20 pass + 30 rush = 50 plays too -- no plays delta.
    assert result.plays_delta == 0
    # Prior pass rate: 20/50 = 40%. Current: 30/50 = 60%. Delta = +20.0.
    assert result.pass_rate_delta == 20.0


# -- team_projected_ownership_pct / combined_projected_ownership_pct --


def test_team_projected_ownership_pct_sums_skill_positions_excludes_dst():
    ownership_players = [
        _ownership_player("LAC QB1", "QB", "LAC", 20.0),
        _ownership_player("LAC RB1", "RB", "LAC", 15.5),
        _ownership_player("LAC DST", "DST", "LAC", 10.0),
        _ownership_player("DEN QB1", "QB", "DEN", 25.0),
    ]
    assert team_projected_ownership_pct("LAC", ownership_players) == 35.5


def test_team_projected_ownership_pct_treats_missing_pct_as_zero():
    ownership_players = [_ownership_player("LAC QB1", "QB", "LAC", None), _ownership_player("LAC RB1", "RB", "LAC", 15.0)]
    assert team_projected_ownership_pct("LAC", ownership_players) == 15.0


def test_team_projected_ownership_pct_none_when_no_matching_rows():
    ownership_players = [_ownership_player("DEN QB1", "QB", "DEN", 25.0)]
    assert team_projected_ownership_pct("LAC", ownership_players) is None


def test_combined_projected_ownership_pct_sums_both_sides():
    assert combined_projected_ownership_pct(60.0, 50.0) == 110.0


def test_combined_projected_ownership_pct_treats_missing_side_as_zero():
    assert combined_projected_ownership_pct(60.0, None) == 60.0


def test_combined_projected_ownership_pct_none_when_both_missing():
    assert combined_projected_ownership_pct(None, None) is None


# -- total_to_ownership_ratio / is_high_over_under --


def test_total_to_ownership_ratio_divides_combined_by_over_under():
    assert total_to_ownership_ratio(110.0, 51.5) == round(110.0 / 51.5, 2)
    assert total_to_ownership_ratio(35.0, 49.5) == round(35.0 / 49.5, 2)


def test_total_to_ownership_ratio_none_when_either_input_missing():
    assert total_to_ownership_ratio(None, 51.5) is None
    assert total_to_ownership_ratio(110.0, None) is None


def test_total_to_ownership_ratio_none_when_over_under_zero():
    assert total_to_ownership_ratio(110.0, 0) is None


def test_is_high_over_under_true_at_or_above_47():
    assert is_high_over_under(47.0) is True
    assert is_high_over_under(51.5) is True


def test_is_high_over_under_false_below_47_or_missing():
    assert is_high_over_under(46.5) is False
    assert is_high_over_under(None) is False


def test_is_low_over_under_true_at_or_below_40():
    assert is_low_over_under(40.0) is True
    assert is_low_over_under(39.5) is True
    assert is_low_over_under(30.0) is True


def test_is_low_over_under_false_above_40_or_missing():
    assert is_low_over_under(40.5) is False
    assert is_low_over_under(44.5) is False
    assert is_low_over_under(None) is False


def test_compute_ownership_bands_none_below_min_sample_size():
    # MIN_BAND_SAMPLE_SIZE is 4 -- 3 values isn't enough to rank
    # meaningfully (and statistics.quantiles itself would still work here,
    # but the whole point is not trusting a percentile computed over a
    # handful of values).
    assert compute_ownership_bands([10.0, 20.0, 30.0]) is None


def test_compute_ownership_bands_returns_33rd_67th_percentile():
    # Verified via statistics.quantiles([5, 10, 15, 20, 60, 65, 90, 95],
    # n=3, method="inclusive") == [16.666..., 63.333...].
    bands = compute_ownership_bands([5.0, 10.0, 15.0, 20.0, 60.0, 65.0, 90.0, 95.0])
    assert bands == (50.0 / 3, 190.0 / 3)


def test_classify_by_bands_low_at_or_below_cutoff():
    bands = (50.0 / 3, 190.0 / 3)
    assert classify_by_bands(50.0 / 3, bands) == "low"
    assert classify_by_bands(5.0, bands) == "low"


def test_classify_by_bands_high_at_or_above_cutoff():
    bands = (50.0 / 3, 190.0 / 3)
    assert classify_by_bands(190.0 / 3, bands) == "high"
    assert classify_by_bands(95.0, bands) == "high"


def test_classify_by_bands_none_in_the_middle_or_missing_inputs():
    bands = (50.0 / 3, 190.0 / 3)
    assert classify_by_bands(40.0, bands) is None
    assert classify_by_bands(None, bands) is None
    assert classify_by_bands(40.0, None) is None


def test_pace_trend_skips_bye_week_gap_to_find_most_recent_played_week():
    # No stat lines at all for week 10 (bye) -- most recent played week is 9.
    stat_lines_by_position = {
        "QB": {("LAC QB", 9): {"team": "LAC", "pass_att": 25}},
        "RB": {("LAC RB", 9): {"team": "LAC", "rush_att": 25}},
    }
    result = build_team_pace_trend("LAC", 11, stat_lines_by_position)
    assert result is not None
    assert result.week == 9
    assert result.plays == 50
