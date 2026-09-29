from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.schemas.game_preview.game_preview import GamePreviewPositionalMatchup
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.usage_bump.usage_bump import UsageBump, UsageBumpCause
from backend.services.game_preview.game_preview_player_tags import build_team_player_tags
from backend.services.schedule.schedule_loader import parse_schedule_csv

SCHEDULE_CSV = (
    "Team,Week,Opponent,GameLocation\n"
    "LAC,10,DEN,Away\n"
    "DEN,10,LAC,Home\n"
    "LAC,9,KC,Home\n"
    "DEN,9,MIA,Away\n"
)


def _schedule_rows():
    return parse_schedule_csv(SCHEDULE_CSV)


def _tracker_row(name, position, team, week, salary=8000, fpts=0.0, non_td_fpts=0.0, td_fpts=0.0, pct_drafted=10.0):
    return DkPlayerRow(
        name=name,
        position=position,
        roster_position=position,
        team=team,
        week=week,
        salary=salary,
        pct_drafted=pct_drafted,
        fpts=fpts,
        non_td_fpts=non_td_fpts,
        td_fpts=td_fpts,
    )


def _bump(player, team, position="RB", rank=2, bump_score=1.0, cause_player="Starter", cause_status="Out"):
    return UsageBump(
        team_abbrev=team,
        position=position,
        player=player,
        rank=rank,
        bump_score=bump_score,
        causes=[
            UsageBumpCause(
                player=cause_player,
                status=cause_status,
                position=position,
                rank=1,
                weight=1.0,
                player_out_depths=[0],
                usage_bump_list=[],
                source="curated",
            )
        ],
    )


def _ownership(player, team, position="WR", ownership_pct=None):
    return OwnershipPlayer(
        player=player, position=position, team=team, opponent="X", salary=6000, ownership_pct=ownership_pct
    )


def test_repeat_performer_fade_tag_fires_on_two_high_multiplier_weeks():
    # base week = 10 (week param 11, since build_multiplier_rows uses week-1).
    tracker_rows = [
        _tracker_row("Star WR", "WR", "LAC", 10, salary=8000, fpts=32.0),  # 4.0x
        _tracker_row("Star WR", "WR", "LAC", 9, salary=8000, fpts=36.0),  # 4.5x
    ]
    players = build_team_player_tags(
        "LAC", tracker_rows, _schedule_rows(), 11, 5, {}, [], []
    )
    assert len(players) == 1
    tags = players[0].tags
    assert any(t.kind == "fade" and "Repeat Performer" in t.reason for t in tags)


def test_repeat_performer_label_counts_only_played_weeks_not_window_size():
    # window_weeks=5 means the nominal window is 6 slots (base + 5
    # trailing), but only 2 weeks of tracker data actually exist here --
    # the label should say "2 of the last 2 weeks played", not "...6
    # weeks shown", since only 2 games have actually been played this
    # season (the exact bug this test guards against).
    tracker_rows = [
        _tracker_row("CIN DST", "DST", "CIN", 2, salary=3000, fpts=16.0),  # 5.33x
        _tracker_row("CIN DST", "DST", "CIN", 1, salary=3000, fpts=15.0),  # 5.0x
    ]
    schedule_rows = parse_schedule_csv(
        "Team,Week,Opponent,GameLocation\nCIN,3,DEN,Away\nDEN,3,CIN,Home\nCIN,2,KC,Home\nDEN,2,MIA,Away\n"
        "CIN,1,NYJ,Home\nDEN,1,NYJ,Away\n"
    )
    players = build_team_player_tags("CIN", tracker_rows, schedule_rows, 3, 5, {}, [], [])
    assert len(players) == 1
    reason = next(t.reason for t in players[0].tags if t.kind == "fade")
    assert "2 of the last 2 weeks played" in reason
    assert "6 weeks" not in reason


def test_depth_by_name_populates_player_depth():
    tracker_rows = [
        _tracker_row("Star WR", "WR", "LAC", 10, salary=8000, fpts=32.0),
        _tracker_row("Star WR", "WR", "LAC", 9, salary=8000, fpts=36.0),
    ]
    players = build_team_player_tags(
        "LAC", tracker_rows, _schedule_rows(), 11, 5, {}, [], [], depth_by_name={"Star WR": 1}
    )
    assert len(players) == 1
    assert players[0].depth == 1


def test_depth_defaults_to_none_when_not_supplied():
    tracker_rows = [
        _tracker_row("Star WR", "WR", "LAC", 10, salary=8000, fpts=32.0),
        _tracker_row("Star WR", "WR", "LAC", 9, salary=8000, fpts=36.0),
    ]
    players = build_team_player_tags("LAC", tracker_rows, _schedule_rows(), 11, 5, {}, [], [])
    assert players[0].depth is None


def test_breakout_watch_play_tag_fires_on_two_weeks_high_non_td_zero_td():
    tracker_rows = [
        _tracker_row("Backup RB", "RB", "LAC", 10, salary=5000, fpts=15.0, non_td_fpts=15.0, td_fpts=0.0),  # 3.0x
        _tracker_row("Backup RB", "RB", "LAC", 9, salary=5000, fpts=17.5, non_td_fpts=17.5, td_fpts=0.0),  # 3.5x
    ]
    players = build_team_player_tags("LAC", tracker_rows, _schedule_rows(), 11, 5, {}, [], [])
    assert len(players) == 1
    tags = players[0].tags
    assert any(t.kind == "play" and "Breakout Watch" in t.reason for t in tags)


def test_share_trend_rise_gives_play_tag():
    tracker_rows = [_tracker_row("Slot WR", "WR", "LAC", 10, salary=6000, fpts=10.0)]
    stat_lines_by_position = {
        "WR": {
            ("Slot WR", 10): {"target_share_pct": 30.0, "touch_share_pct": 25.0, "opp_share_pct": 20.0},
            ("Slot WR", 9): {"target_share_pct": 20.0, "touch_share_pct": 18.0, "opp_share_pct": 15.0},
        }
    }
    players = build_team_player_tags(
        "LAC", tracker_rows, _schedule_rows(), 11, 5, stat_lines_by_position, [], []
    )
    assert len(players) == 1
    tags = players[0].tags
    assert any(t.kind == "play" and "Rising" in t.reason for t in tags)


def test_share_trend_fall_gives_monitor_tag():
    tracker_rows = [_tracker_row("Fading WR", "WR", "LAC", 10, salary=6000, fpts=10.0)]
    stat_lines_by_position = {
        "WR": {
            ("Fading WR", 10): {"target_share_pct": 10.0, "touch_share_pct": 8.0, "opp_share_pct": 5.0},
            ("Fading WR", 9): {"target_share_pct": 20.0, "touch_share_pct": 18.0, "opp_share_pct": 15.0},
        }
    }
    players = build_team_player_tags(
        "LAC", tracker_rows, _schedule_rows(), 11, 5, stat_lines_by_position, [], []
    )
    assert len(players) == 1
    tags = players[0].tags
    assert any(t.kind == "monitor" and "Falling" in t.reason for t in tags)


def test_usage_bump_gives_play_tag_and_appears_even_without_multiplier_row():
    bumps = [_bump("Backup RB", "LAC", bump_score=1.5, cause_player="Starter RB", cause_status="Out")]
    players = build_team_player_tags("LAC", [], _schedule_rows(), 11, 5, {}, [], bumps)
    assert len(players) == 1
    assert players[0].name == "Backup RB"
    tags = players[0].tags
    assert any(t.kind == "play" and "Usage bump" in t.reason and "Starter RB" in t.reason for t in tags)


def test_usage_bump_with_zero_score_does_not_produce_a_row():
    bumps = [_bump("Healthy Backup", "LAC", bump_score=0.0)]
    players = build_team_player_tags("LAC", [], _schedule_rows(), 11, 5, {}, [], bumps)
    assert players == []


def test_usage_bump_reason_says_out_for_confirmed_out_status_code():
    bumps = [_bump("Backup WR", "LAC", cause_player="Demarcus Robinson", cause_status="O")]
    players = build_team_player_tags("LAC", [], _schedule_rows(), 11, 5, {}, [], bumps)
    reason = players[0].tags[0].reason
    assert reason == "Usage bump with Demarcus Robinson (O) out -- extra volume likely"


def test_usage_bump_reason_says_if_sits_for_questionable_or_doubtful():
    bumps = [_bump("Backup WR", "LAC", cause_player="Demarcus Robinson", cause_status="Q")]
    players = build_team_player_tags("LAC", [], _schedule_rows(), 11, 5, {}, [], bumps)
    reason = players[0].tags[0].reason
    assert reason == "Usage bump if Demarcus Robinson (Q) sits -- extra volume likely"


def test_low_ownership_gives_leverage_tag():
    ownership = [_ownership("Deep Sleeper", "LAC", ownership_pct=2.0)]
    players = build_team_player_tags("LAC", [], _schedule_rows(), 11, 5, {}, ownership, [])
    assert len(players) == 1
    tags = players[0].tags
    assert any(t.kind == "leverage" for t in tags)


def test_high_ownership_gives_chalk_tag():
    ownership = [_ownership("Popular Chalk", "LAC", ownership_pct=30.0)]
    players = build_team_player_tags("LAC", [], _schedule_rows(), 11, 5, {}, ownership, [])
    assert len(players) == 1
    tags = players[0].tags
    assert any(t.kind == "chalk" for t in tags)


def test_mid_ownership_produces_no_tag_and_no_row():
    ownership = [_ownership("Middling Owned", "LAC", ownership_pct=15.0)]
    players = build_team_player_tags("LAC", [], _schedule_rows(), 11, 5, {}, ownership, [])
    assert players == []


def test_no_signal_no_row():
    # A tracker row with only one week (no trend possible) and nothing else.
    tracker_rows = [_tracker_row("Quiet Player", "WR", "LAC", 10, salary=6000, fpts=5.0)]
    players = build_team_player_tags("LAC", tracker_rows, _schedule_rows(), 11, 5, {}, [], [])
    assert players == []


def test_positional_matchup_gives_play_tag_when_opponent_position_exploitable():
    tracker_rows = [_tracker_row("Slot WR", "WR", "LAC", 10, salary=6000, fpts=10.0)]
    exploitable = [
        GamePreviewPositionalMatchup(
            position="WR", games=3, avg_fpts_allowed=22.5, league_avg_fpts=15.0, high_multiplier_games=2
        )
    ]
    players = build_team_player_tags(
        "LAC",
        tracker_rows,
        _schedule_rows(),
        11,
        5,
        {},
        [],
        [],
        opponent="DEN",
        opponent_exploitable_positions=exploitable,
    )
    assert len(players) == 1
    tags = players[0].tags
    matchup_tags = [t for t in tags if t.kind == "play" and "DEN has allowed" in t.reason]
    assert len(matchup_tags) == 1
    assert "22.5 FPTS/game to WRs" in matchup_tags[0].reason
    assert "league avg 15.0" in matchup_tags[0].reason


def test_positional_matchup_tag_not_fired_for_non_matching_position():
    tracker_rows = [_tracker_row("Slot WR", "WR", "LAC", 10, salary=6000, fpts=10.0)]
    exploitable = [
        GamePreviewPositionalMatchup(
            position="RB", games=3, avg_fpts_allowed=22.5, league_avg_fpts=15.0, high_multiplier_games=2
        )
    ]
    players = build_team_player_tags(
        "LAC",
        tracker_rows,
        _schedule_rows(),
        11,
        5,
        {},
        [],
        [],
        opponent="DEN",
        opponent_exploitable_positions=exploitable,
    )
    assert players == []


def test_positional_matchup_tag_absent_when_no_exploitable_positions_supplied():
    tracker_rows = [_tracker_row("Slot WR", "WR", "LAC", 10, salary=6000, fpts=10.0)]
    players = build_team_player_tags("LAC", tracker_rows, _schedule_rows(), 11, 5, {}, [], [])
    assert players == []


def test_player_universe_is_union_of_three_sources_scoped_to_team():
    tracker_rows = [
        _tracker_row("Star WR", "WR", "LAC", 10, salary=8000, fpts=32.0),
        _tracker_row("Star WR", "WR", "LAC", 9, salary=8000, fpts=36.0),
        # Different team -- should not appear when scoped to LAC.
        _tracker_row("Other Team Player", "WR", "DEN", 10, salary=8000, fpts=32.0),
        _tracker_row("Other Team Player", "WR", "DEN", 9, salary=8000, fpts=36.0),
    ]
    bumps = [_bump("Bump Beneficiary", "LAC", bump_score=1.0)]
    ownership = [_ownership("Chalk Play", "LAC", ownership_pct=40.0)]

    players = build_team_player_tags("LAC", tracker_rows, _schedule_rows(), 11, 5, {}, ownership, bumps)
    names = {p.name for p in players}
    assert names == {"Star WR", "Bump Beneficiary", "Chalk Play"}
