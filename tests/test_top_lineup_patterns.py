from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.contest_results.contest_standings_parser import (
    ContestEntry,
    ContestReferenceRow,
    ContestStandings,
)
from backend.services.lineup_scenarios.top_lineup_patterns import WeekInput, analyze_top_lineups

# name -> (position, team, opponent, salary, own%)
_PLAYERS = {
    "Q1": ("QB", "AAA", "BBB", 6000, 10.0),
    "R1": ("RB", "AAA", "BBB", 7000, 20.0),
    "W1": ("WR", "AAA", "BBB", 6000, 30.0),
    "W2": ("WR", "BBB", "AAA", 5500, 5.0),
    "R2": ("RB", "CCC", "DDD", 5000, 15.0),
    "W3": ("WR", "CCC", "DDD", 4000, 25.0),
    "T1": ("TE", "DDD", "CCC", 3500, 8.0),
    "F1": ("RB", "EEE", "FFF", 4500, 12.0),
    "Dst1": ("DST", "FFF", "EEE", 2500, 9.0),
}
_LINEUP = "DST Dst1 FLEX F1 QB Q1 RB R1 RB R2 TE T1 WR W1 WR W2 WR W3"


def _salary_players(names=None):
    return [
        OwnershipPlayer(player=n, position=pos, team=team, opponent=opp, salary=sal)
        for n, (pos, team, opp, sal, _own) in _PLAYERS.items()
        if names is None or n in names
    ]


def _standings(lineups, points=200.0):
    entries = [
        ContestEntry(rank=i + 1, entry_id=str(i), entry_name="x", points=points, lineup_text=text)
        for i, text in enumerate(lineups)
    ]
    refs = [
        ContestReferenceRow(player=n, roster_position=pos, pct_drafted=own, fpts=10.0)
        for n, (pos, _t, _o, _s, own) in _PLAYERS.items()
    ]
    return ContestStandings(entries=entries, reference_rows=refs)


def _category(result, key):
    return next(c for c in result.categories if c.key == key)


def _stat(result, key, pattern):
    return next(p for p in _category(result, key).patterns if p.pattern == pattern)


def _analyze(lineups=(_LINEUP,), **kwargs):
    inputs = [WeekInput(week=1, standings=_standings(list(lineups)), salary_players=_salary_players())]
    return analyze_top_lineups(inputs, top_n=1000, **kwargs)


def test_flex_and_qb_stack_patterns_with_trend_columns():
    result = _analyze()
    assert result.lineups_analyzed == 1
    assert _stat(result, "flex", "FLEX = RB").count == 1

    size = _stat(result, "stack_size", "QB + 2 teammates")
    assert size.count == 1 and size.pct_of_lineups == 100.0

    stack = _stat(result, "qb_stack", "QB + RB + WR")
    assert stack.avg_ownership_pct == 20.0  # mean of Q1 10, R1 20, W1 30
    assert stack.avg_salary_total == 19000  # 6000 + 7000 + 6000
    assert stack.avg_points == 200.0
    assert stack.by_week == {1: 1}


def test_bring_back_and_game_stack():
    result = _analyze()
    bring = _stat(result, "bring_back", "Bring-back: WR")
    assert bring.avg_salary_total == 5500
    assert bring.avg_ownership_pct == 5.0
    assert _stat(result, "game_stack", "QB + RB + WR | Bring-back: WR").avg_salary_total == 24500


def test_no_bring_back_has_no_ownership_or_salary():
    lineup = "DST Dst1 FLEX F1 QB Q1 RB R1 RB R2 TE T1 WR W1 WR W3 WR W3"
    result = _analyze([lineup])
    stat = _stat(result, "bring_back", "No bring-back")
    assert stat.avg_ownership_pct is None
    assert stat.avg_salary_total is None


def test_other_game_and_other_team_stacks():
    result = _analyze()
    assert _stat(result, "other_game_stack", "RB + WR vs TE").count == 1
    assert _stat(result, "other_team_stack", "RB + WR").count == 1


def test_dst_patterns():
    result = _analyze()
    assert _stat(result, "dst_vs", "DST vs RB").count == 1  # DST faces EEE's F1
    assert _stat(result, "dst_with", "DST with no own offense").count == 1


def test_salary_shape_and_unused_salary():
    result = _analyze()
    assert _stat(result, "salary_shape", "0 stars / 2 punts").count == 1  # W3 4000, T1 3500
    left = _stat(result, "salary_left", "$500+ left")
    assert left.avg_salary_total == 44000  # whole lineup


def test_lineup_with_unresolved_player_is_skipped():
    inputs = [
        WeekInput(
            week=1,
            standings=_standings([_LINEUP]),
            salary_players=_salary_players(names=set(_PLAYERS) - {"T1"}),
        )
    ]
    result = analyze_top_lineups(inputs, top_n=1000)
    assert result.lineups_analyzed == 0
    assert result.lineups_skipped == 1


def test_counts_accumulate_by_week_and_top_n_limits():
    inputs = [
        WeekInput(week=1, standings=_standings([_LINEUP, _LINEUP]), salary_players=_salary_players()),
        WeekInput(week=2, standings=_standings([_LINEUP]), salary_players=_salary_players()),
    ]
    result = analyze_top_lineups(inputs, top_n=1, weeks_missing=[3])
    assert result.lineups_by_week == {1: 1, 2: 1}  # top_n=1 per week
    assert result.weeks_missing == [3]
    stat = _stat(result, "flex", "FLEX = RB")
    assert stat.count == 2 and stat.by_week == {1: 1, 2: 1}


def test_max_patterns_caps_each_category():
    other = "DST Dst1 FLEX F1 QB Q1 RB R1 RB R2 TE T1 WR W1 WR W3 WR W3"
    inputs = [WeekInput(week=1, standings=_standings([_LINEUP, other]), salary_players=_salary_players())]
    result = analyze_top_lineups(inputs, top_n=1000, max_patterns=1)
    category = _category(result, "bring_back")
    assert category.distinct_patterns == 2
    assert len(category.patterns) == 1
