import pytest

from backend.repositories.ownership.leverage_tiers_repo import LeverageTier
from backend.schemas.ownership.ownership import GameLeverageGroup, OwnershipPlayer, OwnershipSnapshot, PivotGroup
from backend.services.ownership.engine import (
    compute_game_leverage,
    compute_high_owned,
    compute_multi_leverage,
    compute_ownership_diff,
    compute_pivots,
)

TIERS = [
    LeverageTier(min_games=1, max_games=1, leverage_point=50.0),
    LeverageTier(min_games=2, max_games=2, leverage_point=40.0),
    LeverageTier(min_games=3, max_games=4, leverage_point=35.0),
]


def make_player(player, position, team, opponent, salary, ownership_pct, is_home=True):
    return OwnershipPlayer(
        player=player,
        position=position,
        team=team,
        opponent=opponent,
        is_home=is_home,
        salary=salary,
        ownership_pct=ownership_pct,
    )


def test_compute_high_owned_resolves_tier_by_game_count():
    # 4 unique teams -> 2 games -> tier says 40.0.
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000, 45.0),
        make_player("B", "WR", "ARI", "HOU", 5000, 10.0),
        make_player("C", "WR", "SF", "LAR", 5000, 39.9),
        make_player("D", "RB", "LAR", "SF", 5000, 5.0),
    ]
    high_owned, leverage_point = compute_high_owned(players, TIERS)
    assert leverage_point == 40.0
    assert [p.player for p in high_owned] == ["A"]


def test_compute_high_owned_no_matching_tier_raises():
    players = [make_player("A", "RB", "HOU", "ARI", 5000, 45.0)] * 1
    # 1 team only -> 0.5 games -- below every configured tier's min_games.
    with pytest.raises(ValueError):
        compute_high_owned(players, TIERS)


def test_compute_game_leverage_groups_by_game_and_requires_chalk():
    players = [
        make_player("Chalk", "RB", "HOU", "ARI", 5000, 45.0),
        make_player("Teammate", "WR", "HOU", "ARI", 5000, 10.0),
        make_player("Opponent", "WR", "ARI", "HOU", 5000, 5.0),
        make_player("NoChalkHere", "RB", "SF", "LAR", 5000, 20.0),
        make_player("AlsoNoChalk", "RB", "LAR", "SF", 5000, 15.0),
    ]
    groups = compute_game_leverage(players, leverage_point=40.0)

    # Only the HOU/ARI game has a chalk player -- SF/LAR is dropped entirely.
    assert len(groups) == 1
    group = groups[0]
    assert {group.team, group.opponent} == {"HOU", "ARI"}
    assert [p.player for p in group.chalk_players] == ["Chalk"]
    assert {p.player for p in group.pivot_candidates} == {"Teammate", "Opponent"}


def test_compute_game_leverage_excludes_qb_and_dst_from_chalk_and_pivots():
    players = [
        make_player("ChalkRB", "RB", "HOU", "ARI", 5000, 45.0),
        make_player("ChalkQB", "QB", "HOU", "ARI", 6000, 42.0),
        make_player("PivotWR", "WR", "HOU", "ARI", 5000, 10.0),
        make_player("PivotDST", "DST", "ARI", "HOU", 3000, 8.0),
    ]
    groups = compute_game_leverage(players, leverage_point=40.0)

    assert len(groups) == 1
    group = groups[0]
    assert [p.player for p in group.chalk_players] == ["ChalkRB"]
    assert [p.player for p in group.pivot_candidates] == ["PivotWR"]


def test_compute_game_leverage_drops_game_whose_only_chalk_is_excluded():
    players = [
        make_player("OnlyChalkIsQB", "QB", "HOU", "ARI", 6000, 45.0),
        make_player("LowOwnedWR", "WR", "HOU", "ARI", 5000, 10.0),
    ]
    groups = compute_game_leverage(players, leverage_point=40.0)
    assert groups == []


def test_compute_pivots_matches_salary_and_ownership_thresholds():
    trigger = make_player("Trigger", "RB", "HOU", "ARI", 6000, 30.0)
    close_low_owned = make_player("Pivot1", "RB", "SF", "LAR", 5600, 15.0)  # within $500, -15pts
    too_far_salary = make_player("TooExpensive", "RB", "SF", "LAR", 6600, 5.0)  # $600 away
    not_enough_gap = make_player("StillChalky", "RB", "SF", "LAR", 5800, 25.0)  # only -5pts
    wrong_position = make_player("WrongPos", "WR", "SF", "LAR", 5900, 5.0)

    players = [trigger, close_low_owned, too_far_salary, not_enough_gap, wrong_position]
    groups = compute_pivots(players)

    trigger_group = next(g for g in groups if g.trigger.player == "Trigger")
    assert [p.player for p in trigger_group.pivots] == ["Pivot1"]


def test_compute_pivots_omits_players_with_no_qualifying_pivot():
    lonely = make_player("Lonely", "TE", "HOU", "ARI", 3000, 10.0)
    groups = compute_pivots([lonely])
    assert groups == []


def test_compute_pivots_sorted_by_salary_descending():
    trigger = make_player("Trigger", "WR", "HOU", "ARI", 7000, 30.0)
    low = make_player("Low", "WR", "SF", "LAR", 6600, 5.0)
    high = make_player("High", "WR", "SF", "LAR", 7400, 2.0)
    groups = compute_pivots([trigger, low, high])
    trigger_group = next(g for g in groups if g.trigger.player == "Trigger")
    assert [p.player for p in trigger_group.pivots] == ["High", "Low"]


def test_compute_multi_leverage_combines_pivot_and_game_reasons():
    # A player who's a pivot for one trigger AND a game-leverage pick
    # against one chalk player already has 2 reasons of different kinds.
    subject = make_player("Deebo", "WR", "SF", "LAR", 6100, 20.0)
    pivot_trigger = make_player("Christian Watson", "WR", "GB", "CHI", 6500, 32.0)
    chalk = make_player("CMC", "RB", "SF", "LAR", 9000, 30.0)

    pivots = [PivotGroup(trigger=pivot_trigger, pivots=[subject])]
    game_leverage = [
        GameLeverageGroup(team="LAR", opponent="SF", chalk_players=[chalk], pivot_candidates=[subject])
    ]

    results = compute_multi_leverage(pivots, game_leverage)

    assert [r.player.player for r in results] == ["Deebo"]
    entry = results[0]
    assert len(entry.reasons) == 2
    kinds = {r.kind for r in entry.reasons}
    assert kinds == {"pivot", "game"}
    pivot_reason = next(r for r in entry.reasons if r.kind == "pivot")
    assert pivot_reason.against.player == "Christian Watson"
    game_reason = next(r for r in entry.reasons if r.kind == "game")
    assert game_reason.against.player == "CMC"
    assert game_reason.team == "LAR"
    assert game_reason.opponent == "SF"


def test_compute_multi_leverage_one_reason_per_chalk_player_in_game():
    # A single game with 2 chalk players is worth 2 reasons on its own.
    candidate = make_player("Pivot", "WR", "SF", "LAR", 5000, 10.0)
    chalk_a = make_player("ChalkA", "RB", "SF", "LAR", 9000, 40.0)
    chalk_b = make_player("ChalkB", "WR", "LAR", "SF", 8000, 35.0)

    game_leverage = [
        GameLeverageGroup(team="LAR", opponent="SF", chalk_players=[chalk_a, chalk_b], pivot_candidates=[candidate])
    ]
    results = compute_multi_leverage(pivots=[], game_leverage=game_leverage)

    assert len(results) == 1
    assert len(results[0].reasons) == 2
    assert {r.against.player for r in results[0].reasons} == {"ChalkA", "ChalkB"}


def test_compute_multi_leverage_excludes_players_with_only_one_reason():
    subject = make_player("OnlyOneReason", "RB", "SF", "LAR", 5000, 10.0)
    trigger = make_player("Trigger", "RB", "GB", "CHI", 5200, 25.0)
    results = compute_multi_leverage(pivots=[PivotGroup(trigger=trigger, pivots=[subject])], game_leverage=[])
    assert results == []


def test_compute_multi_leverage_sorted_by_reason_count_then_salary():
    trigger_a = make_player("TriggerA", "RB", "GB", "CHI", 5200, 25.0)
    trigger_b = make_player("TriggerB", "RB", "NYJ", "MIA", 5300, 26.0)
    chalk = make_player("Chalk", "WR", "SF", "LAR", 9000, 40.0)

    two_reasons_high_salary = make_player("TwoReasonsHigh", "RB", "SF", "LAR", 6000, 5.0)
    two_reasons_low_salary = make_player("TwoReasonsLow", "RB", "SF", "LAR", 4000, 5.0)
    one_reason = make_player("OneReason", "RB", "SF", "LAR", 7000, 5.0)

    pivots = [
        PivotGroup(trigger=trigger_a, pivots=[two_reasons_high_salary, two_reasons_low_salary, one_reason]),
        PivotGroup(trigger=trigger_b, pivots=[two_reasons_high_salary, two_reasons_low_salary]),
    ]
    results = compute_multi_leverage(pivots=pivots, game_leverage=[])

    assert [r.player.player for r in results] == ["TwoReasonsHigh", "TwoReasonsLow"]


def make_snapshot(players, season=2025, week=15, scraped_at="2026-08-07T08:00:00-04:00"):
    return OwnershipSnapshot(
        scraped_at=scraped_at, source_url="https://example.com", season=season, week=week, players=players
    )


def test_compute_ownership_diff_detects_ownership_and_salary_changes():
    old_snapshot = make_snapshot([make_player("A", "RB", "HOU", "ARI", 5000, 10.0)])
    new_snapshot = make_snapshot([make_player("A", "RB", "HOU", "ARI", 5200, 15.0)])

    changes = compute_ownership_diff(old_snapshot, new_snapshot)
    assert len(changes) == 1
    change = changes[0]
    assert set(change.change_types) == {"ownership", "salary"}
    assert change.previous_ownership_pct == 10.0
    assert change.current_ownership_pct == 15.0
    assert change.previous_salary == 5000
    assert change.current_salary == 5200


def test_compute_ownership_diff_no_change_produces_no_entry():
    player = make_player("A", "RB", "HOU", "ARI", 5000, 10.0)
    changes = compute_ownership_diff(make_snapshot([player]), make_snapshot([player]))
    assert changes == []


def test_compute_ownership_diff_added_and_removed_players():
    old_snapshot = make_snapshot([make_player("Gone", "RB", "HOU", "ARI", 5000, 10.0)])
    new_snapshot = make_snapshot([make_player("New", "WR", "HOU", "ARI", 4000, 5.0)])

    changes = compute_ownership_diff(old_snapshot, new_snapshot)
    by_player = {c.player: c for c in changes}

    assert by_player["Gone"].change_types == ["other"]
    assert by_player["Gone"].previous_ownership_pct == 10.0
    assert by_player["Gone"].current_ownership_pct is None

    assert by_player["New"].change_types == ["other"]
    assert by_player["New"].current_ownership_pct == 5.0


# Ownership projections lag DK salaries by a few days (see
# OwnershipPlayer.ownership_pct's docstring) -- a snapshot with
# salary/position but no ownership yet shouldn't crash any of these, it
# should just leave the ownership-dependent players out of the
# classification.


def test_compute_high_owned_excludes_players_with_no_ownership_pct():
    # 2 teams -> 1 game -> tier says 50.0 (see TIERS above).
    players = [
        make_player("Known", "RB", "HOU", "ARI", 5000, 55.0),
        make_player("Unknown", "WR", "ARI", "HOU", 5000, None),
    ]
    high_owned, _ = compute_high_owned(players, TIERS)
    assert [p.player for p in high_owned] == ["Known"]


def test_compute_game_leverage_excludes_players_with_no_ownership_pct():
    players = [
        make_player("Chalk", "RB", "HOU", "ARI", 5000, 45.0),
        make_player("Unknown", "WR", "HOU", "ARI", 5000, None),
    ]
    groups = compute_game_leverage(players, leverage_point=40.0)
    assert len(groups) == 1
    assert [p.player for p in groups[0].chalk_players] == ["Chalk"]
    # "Unknown" has no ownership_pct, so it can't be confirmed as below
    # the leverage point either -- excluded from pivot_candidates too.
    assert groups[0].pivot_candidates == []


def test_compute_pivots_trigger_with_no_ownership_pct_produces_no_group():
    players = [
        make_player("Trigger", "RB", "HOU", "ARI", 5000, None),
        make_player("Candidate", "RB", "ARI", "HOU", 5000, 5.0),
    ]
    assert compute_pivots(players) == []


def test_compute_pivots_candidate_with_no_ownership_pct_excluded():
    players = [
        make_player("Trigger", "RB", "HOU", "ARI", 5000, 45.0),
        make_player("Unknown", "RB", "ARI", "HOU", 5000, None),
    ]
    assert compute_pivots(players) == []
