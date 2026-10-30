from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.leverage_pivots.engine import (
    build_chalk_groups,
    build_panel,
    build_selected,
    correlated_for,
    leverage_for,
    position_pivots_for,
    pricing_pivots_for,
)

LP = 20.0


def p(name, pos, team, opp, salary, own):
    return OwnershipPlayer(player=name, position=pos, team=team, opponent=opp, salary=salary, ownership_pct=own)


BIJAN = p("Bijan", "RB", "ATL", "TB", 8500, 30.0)
LONDON = p("London", "WR", "ATL", "TB", 7000, 25.0)
PITTS = p("Pitts", "TE", "ATL", "TB", 4500, 2.0)
PENIX = p("Penix", "QB", "ATL", "TB", 5500, 3.0)
ATL_DST = p("Falcons", "DST", "ATL", "TB", 2800, 4.0)
BUCS_DST = p("Buccaneers", "DST", "TB", "ATL", 2900, 3.0)
EGBUKA = p("Egbuka", "WR", "TB", "ATL", 6400, 12.0)
BAKER = p("Baker", "QB", "TB", "ATL", 5800, 9.0)
HALL = p("Hall", "RB", "NYJ", "BUF", 8200, 4.0)  # RB, -$300, 26 less, other game
WALKER = p("Walker", "RB", "KC", "DEN", 8800, 5.0)
SAMEGAME_RB = p("Irving", "RB", "TB", "ATL", 8400, 1.0)  # same game -> never a pivot
WR_PRICE = p("StBrown", "WR", "DET", "GB", 8000, 6.0)
FAR_RB = p("Far", "RB", "LV", "LAC", 6000, 1.0)  # outside $500
HIGH_OWN_RB = p("Chalk2", "RB", "SF", "SEA", 8300, 25.0)  # not 10 pts less
ALL = [BIJAN, LONDON, PITTS, PENIX, ATL_DST, BUCS_DST, EGBUKA, BAKER, HALL, WALKER, SAMEGAME_RB, WR_PRICE, FAR_RB, HIGH_OWN_RB]


def names(rows):
    return [r.player for r in rows]


def test_leverage_is_own_offense_plus_opposing_dst_below_leverage_point_no_qb():
    got = names(leverage_for(BIJAN, ALL, LP))
    assert set(got) == {"Pitts", "Buccaneers"}  # London is chalk (25 >= 20), Penix is a QB, Falcons is own DST
    # a DST trigger gets the offense it faces, minus QBs and chalk
    popular_dst = p("Bucs2", "DST", "TB", "ATL", 3000, 14.0)
    assert set(names(leverage_for(popular_dst, ALL, LP))) == {"Pitts"}
    # needs a 10-point gap: Buccaneers (3%) vs Pitts (2%) is not leverage
    assert leverage_for(BUCS_DST, ALL, LP) == []


def test_correlated_is_opposing_rb_wr_te_only_sorted_by_ownership():
    assert names(correlated_for(BIJAN, ALL)) == ["Egbuka", "Irving"]  # no QB, no DST, no own team
    assert correlated_for(BUCS_DST, ALL) == []


def test_position_pivot_needs_same_position_price_gap_and_different_game():
    assert names(position_pivots_for(BIJAN, ALL)) == ["Walker", "Hall"]  # by salary desc
    # Irving (same game), Far (price) and Chalk2 (ownership) are excluded


def test_pricing_pivot_is_other_positions_no_qb_different_game():
    assert names(pricing_pivots_for(BIJAN, ALL)) == ["StBrown"]


def test_labels_fraction_percent_and_salary_diff():
    s = build_selected(BIJAN, ALL, LP)
    hall = next(r for r in s.position_pivot.rows if r.player == "Hall")
    assert hall.salary_diff_label == "(−$300)"
    assert hall.less_label == "1/8 · 87% less"  # 30/4 = 7.5 -> 8 ; (30-4)/30 = 86.7 -> 87
    walker = next(r for r in s.position_pivot.rows if r.player == "Walker")
    assert walker.salary_diff_label == "(+$300)"
    assert all(r.less_label is None for r in s.correlated.rows)
    assert s.leverage.header == "ATL + TB DST"
    assert s.position_pivot.header == "RB within $500"
    assert dict(s.position_counts) == {"RB": 3, "WR": 2, "TE": 1, "DST": 1}


def test_position_filter_narrows_rows_but_not_counts():
    s = build_selected(BIJAN, ALL, LP, position="WR")
    assert names(s.correlated.rows) == ["Egbuka"] and names(s.leverage.rows) == [] and names(s.position_pivot.rows) == []
    assert dict(s.position_counts)["RB"] == 3


def test_panel_every_owned_player_is_a_trigger_two_or_more_reasons_no_cap():
    groups = build_panel(ALL, LP)
    by = {pl.player: pl for g in groups for pl in g.players}
    # Hall: position pivot vs Bijan + position pivot vs Chalk2 (8300, 25%; 4 <= 15) + pricing pivot vs London? 7000 vs 8200 > 500 no
    assert {r.label for r in by["Hall"].reasons} == {"Position pivot"} and len(by["Hall"].reasons) == 2
    # Pitts (2%) is leverage against the higher-owned ATL RB/WR: Bijan and London (not QB Penix or the DST)
    assert {r.text.split(" ")[0] for r in by["Pitts"].reasons} == {"Bijan", "London"}
    assert all(r.kind == "leverage" for r in by["Pitts"].reasons)
    assert by["Pitts"].reasons[0].text == "Bijan RB \u00b7 30.0% owned \u00b7 same offense"
    # QBs and DSTs never appear in the panel, as listed players
    assert not {"Penix", "Baker", "Buccaneers", "Falcons"} & set(by)
    # a one-reason player is left out; Far never qualifies
    assert "Far" not in by and "Egbuka" not in by
    assert [g.reason_count for g in groups] == sorted((g.reason_count for g in groups), reverse=True)


def test_chalk_groups_by_position_sorted_by_ownership():
    g = build_chalk_groups([BIJAN, LONDON, HIGH_OWN_RB])
    assert [x.position for x in g] == ["RB", "WR"]
    assert [pl.player for pl in g[0].players] == ["Bijan", "Chalk2"]


def test_panel_min_reasons_filters_groups():
    two_plus = build_panel(ALL, LP, 2)
    three_plus = build_panel(ALL, LP, 3)
    assert min(g.reason_count for g in two_plus) == 2
    assert all(g.reason_count >= 3 for g in three_plus)
    assert {g.reason_count for g in three_plus} <= {g.reason_count for g in two_plus}
