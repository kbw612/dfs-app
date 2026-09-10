from backend.services.shared.name_match import normalize_player_name


def test_lowercases():
    assert normalize_player_name("Joe Mixon") == "joe mixon"


def test_strips_periods_from_initials():
    assert normalize_player_name("D.J. Moore") == normalize_player_name("DJ Moore")
    assert normalize_player_name("A.J. Brown") == normalize_player_name("AJ Brown")


def test_strips_trailing_suffix():
    assert normalize_player_name("Michael Pittman Jr.") == normalize_player_name("Michael Pittman")
    assert normalize_player_name("Odell Beckham Jr") == normalize_player_name("Odell Beckham Jr.")
    assert normalize_player_name("Melvin Gordon III") == normalize_player_name("Melvin Gordon")


def test_does_not_strip_a_suffix_that_is_the_whole_name():
    # A single-word "name" ending in a suffix-looking token (unlikely in
    # practice, but shouldn't collapse to an empty string).
    assert normalize_player_name("III") == "iii"


def test_collapses_extra_whitespace():
    assert normalize_player_name("  Joe   Mixon  ") == "joe mixon"
