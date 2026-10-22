from backend.schemas.dk_players.dk_players import DkPlayerRow
from backend.services.game_logs_summary.position_multipliers import build_position_multipliers
from backend.services.schedule.schedule_loader import parse_schedule_csv

SCHEDULE = parse_schedule_csv(
    "Team,Week,Opponent,GameLocation\n"
    "LAC,1,DEN,Away\n"
    "DEN,1,LAC,Home\n"
    "LAC,2,KC,Home\n"
    "KC,2,LAC,Away\n"
    "DEN,2,MIA,Away\n"
    "MIA,2,DEN,Home\n"
    "LAC,3,DEN,Home\n"
    "DEN,3,LAC,Away\n"
    "KC,3,MIA,Away\n"
    "MIA,3,KC,Home\n"
)


def _row(name, team, week, salary, fpts, non_td, position="RB"):
    return DkPlayerRow(
        name=name,
        position=position,
        roster_position="RB",
        team=team,
        week=week,
        salary=salary,
        pct_drafted=0.0,
        fpts=fpts,
        non_td_fpts=non_td,
        td_fpts=fpts - non_td,
    )


def _rows():
    return [
        # Vidal w1: 24 / 6k = 4.0x (exactly 4x -> 4x+ bucket); non-TD 12/6 = 2.0x (below 2.5x).
        _row("Kimani Vidal", "LAC", 1, 6000, 24.0, 12.0),
        # Vidal w2: 17 / 6k = 2.83x -> below the 3x bar; non-TD 5/6 = 0.83.
        _row("Kimani Vidal", "LAC", 2, 6000, 18.0, 5.0),
        # Williams w1: 2.74x (below 3x); non-TD 12.5/5 = 2.5x (exactly the bar counts).
        _row("Javonte Williams", "DEN", 1, 5000, 13.7, 12.5),
        # Williams w2: below everything.
        _row("Javonte Williams", "DEN", 2, 5000, 8.0, 8.0),
        # Not a RB -- ignored.
        _row("Some WR", "KC", 2, 5000, 40.0, 40.0, position="WR"),
        # Placeholder salary -- ignored.
        _row("Zero Salary", "MIA", 2, 0, 20.0, 20.0),
    ]


def _build(**kwargs):
    kwargs.setdefault("window_weeks", 5)
    return build_position_multipliers(_rows(), SCHEDULE, 3, **kwargs)


def _row_for(result, name):
    return next(r for r in result.rows if r.name == name)


def test_none_when_no_rb_rows():
    assert build_position_multipliers([], SCHEDULE, 3, 5) is None


def test_bucket_boundaries_and_totals():
    result = _build()
    assert result.player_games_4x == 1  # Vidal w1 at exactly 4.0x
    assert result.player_games_3x_399 == 1  # Vidal w2 is exactly 3.0x; Williams 2.74x excluded
    assert result.player_games_non_td_2_5x == 1  # Williams w1 at exactly 2.5x; Vidal's 2.0x is below
    # Allowed side: Vidal w1 faced DEN, Vidal w2 faced KC, Williams w1 faced LAC.
    assert result.defense_allowed_4x == 1
    assert result.defense_allowed_3x_399 == 1
    assert result.defense_allowed_non_td_2_5x == 1


def test_rows_and_defense_lists():
    result = _build()
    assert sorted(r.name for r in result.rows) == ["Javonte Williams", "Kimani Vidal"]

    vidal = _row_for(result, "Kimani Vidal")  # LAC faces DEN in week 3
    assert [(g.week, g.multiplier) for g in vidal.over_4x] == [(1, 4.0)]
    assert [(g.week, g.multiplier, g.is_home, g.salary) for g in vidal.range_3x_399] == [(2, 3.0, True, 6000)]
    assert vidal.non_td_2_5x == []
    # DEN allowed Vidal's 4x game in week 1 (DEN was home).
    assert [(g.week, g.player, g.player_team, g.defense_is_home, g.multiplier, g.salary) for g in vidal.opponent_allowed] == [
        (1, "Kimani Vidal", "LAC", True, 4.0, 6000)
    ]

    williams = _row_for(result, "Javonte Williams")  # DEN faces LAC in week 3
    assert williams.over_4x == [] and williams.range_3x_399 == []
    assert [(g.week, g.multiplier, g.salary) for g in williams.non_td_2_5x] == [(1, 2.5, 5000)]
    # LAC allowed Williams's non-TD 2.5x game; no 3x+ game against LAC.
    assert williams.opponent_allowed == []
    assert [(g.week, g.player) for g in williams.opponent_allowed_non_td] == [(1, "Javonte Williams")]


def test_slate_scoping():
    result = _build(contest_teams={"LAC", "DEN"})
    assert result.player_games_3x_399 == 1
    assert result.defense_allowed_3x_399 == 0  # KC is off the slate


def test_other_positions_use_their_own_rows():
    # "Some WR" (KC, week 2): 40 / 5k = 8.0x, non-TD 8.0x. KC plays MIA in week 3.
    wr = build_position_multipliers(_rows(), SCHEDULE, 3, 5, position="WR")
    assert wr.position == "WR"
    assert [r.name for r in wr.rows] == ["Some WR"]
    assert wr.player_games_4x == 1 and wr.player_games_3x_399 == 0
    assert wr.rows[0].opponent == "MIA"
    # No QBs or TEs in the data.
    assert build_position_multipliers(_rows(), SCHEDULE, 3, 5, position="QB") is None
    assert build_position_multipliers(_rows(), SCHEDULE, 3, 5, position="TE") is None


def test_non_td_column_excludes_games_already_in_multiplier_buckets():
    rows = _rows() + [
        # 30 / 6k = 5.0x (4x+) and non-TD 20 / 6k = 3.33x: counts as 4x+ only.
        _row("Big Game", "LAC", 2, 6000, 30.0, 20.0),
        # 2.9x total (below 3x) with non-TD 2.5x+: counts as non-TD only.
        _row("Near Miss", "LAC", 1, 6000, 17.4, 15.0),
    ]
    result = build_position_multipliers(rows, SCHEDULE, 3, 5)
    big = _row_for(result, "Big Game")
    assert [g.week for g in big.over_4x] == [2]
    assert big.non_td_2_5x == []
    near = _row_for(result, "Near Miss")
    assert near.over_4x == [] and near.range_3x_399 == []
    assert [g.week for g in near.non_td_2_5x] == [1]
    # Defense side too: LAC-bound... Big Game faced KC (w2), Near Miss faced DEN (w1).
    assert [g.player for g in _row_for(result, "Kimani Vidal").opponent_allowed_non_td] == ["Near Miss"]
    assert "Big Game" not in [g.player for r in result.rows for g in r.opponent_allowed_non_td]


def test_rows_are_grouped_by_opponent():
    result = _build()
    opponents = [r.opponent for r in result.rows]
    # Each opponent's rows are contiguous.
    assert opponents == sorted(opponents, key=opponents.index)
    seen = []
    for o in opponents:
        if not seen or seen[-1] != o:
            assert o not in seen
            seen.append(o)
