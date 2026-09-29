from backend.services.weather.scoring import score_weather_color


def test_score_weather_color_red_scores_three():
    assert score_weather_color("red") == 3.0


def test_score_weather_color_orange_scores_three():
    assert score_weather_color("orange") == 3.0


def test_score_weather_color_case_insensitive():
    assert score_weather_color("RED") == 3.0
    assert score_weather_color("Orange") == 3.0


def test_score_weather_color_yellow_scores_two():
    assert score_weather_color("yellow") == 2.0


def test_score_weather_color_green_scores_two():
    assert score_weather_color("green") == 2.0


def test_score_weather_color_unknown_color_scores_two():
    assert score_weather_color("purple") == 2.0
