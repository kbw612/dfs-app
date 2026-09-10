from backend.services.my_player_pool.engine import in_my_player_pool


def test_absent_player_is_not_in_pool():
    assert in_my_player_pool("Josh Allen", {}) is False


def test_explicit_true_is_in_pool():
    assert in_my_player_pool("Josh Allen", {"Josh Allen": True}) is True


def test_explicit_false_is_not_in_pool():
    assert in_my_player_pool("Josh Allen", {"Josh Allen": False}) is False
