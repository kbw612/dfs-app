from backend.services.ownership.scoring import score_dst_ownership_pct, score_ownership_pct


def test_score_ownership_pct_none_when_not_projected():
    assert score_ownership_pct(None) is None


def test_score_ownership_pct_under_ten_scores_three():
    assert score_ownership_pct(9.99) == 3.0
    assert score_ownership_pct(0.0) == 3.0


def test_score_ownership_pct_ten_to_twenty_inclusive_scores_two():
    assert score_ownership_pct(10.0) == 2.0
    assert score_ownership_pct(15.0) == 2.0
    assert score_ownership_pct(20.0) == 2.0


def test_score_ownership_pct_over_twenty_scores_one():
    assert score_ownership_pct(20.01) == 1.0
    assert score_ownership_pct(44.59) == 1.0


def test_score_dst_ownership_pct_none_when_not_projected():
    assert score_dst_ownership_pct(None) is None


def test_score_dst_ownership_pct_two_and_under_scores_three():
    assert score_dst_ownership_pct(2.0) == 3.0
    assert score_dst_ownership_pct(0.0) == 3.0


def test_score_dst_ownership_pct_between_two_and_ten_scores_two():
    assert score_dst_ownership_pct(2.01) == 2.0
    assert score_dst_ownership_pct(5.0) == 2.0
    assert score_dst_ownership_pct(9.99) == 2.0


def test_score_dst_ownership_pct_ten_and_higher_scores_one():
    assert score_dst_ownership_pct(10.0) == 1.0
    assert score_dst_ownership_pct(30.0) == 1.0
