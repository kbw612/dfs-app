from unittest import mock

import backend.services.game_recap.game_recap_scraper as mod
from backend.services.game_recap.game_recap_scraper import (
    _page_matches_week,
    parse_games,
    resolve_away_home,
    resolve_team_abbrev,
    scrape,
)
from backend.services.schedule.schedule_loader import ScheduleRow

# Mirrors the real page's confirmed structure (verified via a live browser
# read of the actual DOM, not a markdown-rendered fetch -- see
# game_recap_scraper.py's own docstring for why that distinction matters):
# each game is its own <div> holding two team-crest <img> tags, a <br>, the
# bold score line, another <br>, and then the recap as BARE TEXT separated
# by <br> tags -- never wrapped in <p> paragraphs. A bylined recap (e.g.
# Charlie Campbell's) adds bare <li> bullets directly among the score
# tag's own siblings -- NOT wrapped in a <ul> at all (confirmed live).
# Each game's own div ends with a boxscore thumbnail image.
_FIXTURE_HTML = """
<html><head><title>NFL Game Recaps: Week 3, 2026 - WalterFootball</title></head>
<body>
<div id="202603___:ATL~GB">
<img src="falconsb_logo.gif"> <img src="packersb_logo.gif">
<br>
<b> Falcons 35, Packers 14 </b> <br>
The Falcons finally had professional quarterbacking with Michael Penix Jr. making his first start.<br> <br>
The Packers turned this opportunity into a score.<br> <br>
<img src="images/fball/nflbox2026_082.jpg">
<br> <br>
</div>

<div id="202603___:SEA~WAS">
<img src="redskinsb_logo.gif"> <img src="seahawksb_logo.gif">
<br>
<b> Redskins 33, Seahawks 31 </b> <br>
The Seahawks were eight-point favorites heading into this game.<br> <br>
<img src="images/fball/nflbox2026_083.jpg">
<br> <br>
</div>

<div id="202603___:NE~JAX">
<img src="patriotsb_logo.gif"> <img src="jaguarsb_logo.gif">
<br>
<b> Jaguars 35, Patriots 6 </b> <br>
By Charlie Campbell - <a href="https://twitter.com/draftcampbell">@draftcampbell</a><br> <br>
<li><em>EDITOR'S NOTE:</em> Drake Maye just keeps getting worse.</li>
<li>The Jaguars controlled this game from start to finish.</li>
<img src="images/fball/nflbox2026_087.jpg">
<br> <br>
</div>

<div id="202603___:LV~XX">
<img src="raidersb_logo.gif"> <img src="dragonsb_logo.gif">
<br>
<b> Raiders 20, Dragons 10 </b> <br>
A fictional opponent, to test the unresolved-team-name path.<br> <br>
<img src="images/fball/nflbox2026_099.jpg">
<br> <br>
</div>

<div id="202603___:ARI~SF">
<img src="49ersb_logo.gif"> <img src="cardinalsb_logo.gif">
<br>
<b> 49ers 36, Cardinals 30 </b> <br>
The 49ers entered this game with Nick Bosa sidelined.<br> <br>
<img src="images/fball/nflbox2026_093.jpg">
<br> <br>
</div>

<p>For more thoughts, check out my updated <strong>NFL Power Rankings</strong>, posted Tuesday.</p>
<p><a href="/picks.php">NFL Picks</a> - Sept. 30</p>
</body></html>
"""

# Matches the real Schedule file's own Team/Week/Opponent/GameLocation
# shape (see schedule_loader.py) for the games above -- SEA@WAS and
# ARI@SF are both deliberately reordered (the site's own score-line text
# lists the home team first in both cases: "Redskins 33, Seahawks 31" and
# "49ers 36, Cardinals 30"), the others keep the scraped order so both
# branches of resolve_away_home get exercised by parse_games' own output
# too.
_SCHEDULE_ROWS = [
    ScheduleRow(team="ATL", week=3, opponent="GB", game_location="Away"),
    ScheduleRow(team="GB", week=3, opponent="ATL", game_location="Home"),
    ScheduleRow(team="SEA", week=3, opponent="WAS", game_location="Away"),
    ScheduleRow(team="WAS", week=3, opponent="SEA", game_location="Home"),
    ScheduleRow(team="NE", week=3, opponent="JAX", game_location="Away"),
    ScheduleRow(team="JAX", week=3, opponent="NE", game_location="Home"),
    ScheduleRow(team="ARI", week=3, opponent="SF", game_location="Away"),
    ScheduleRow(team="SF", week=3, opponent="ARI", game_location="Home"),
    # LV/Dragons deliberately has no schedule rows -- Dragons never
    # resolves to an abbreviation, so it can never match a Team code.
]


def test_parses_every_game_in_document_order():
    games, _ = parse_games(_FIXTURE_HTML)
    assert [g.team_x_name for g in games] == ["Falcons", "Redskins", "Jaguars", "Raiders", "49ers"]
    assert [g.team_y_name for g in games] == ["Packers", "Seahawks", "Patriots", "Dragons", "Cardinals"]


def test_scores_parsed_correctly():
    games, _ = parse_games(_FIXTURE_HTML)
    falcons_game = games[0]
    assert falcons_game.team_x_score == 35
    assert falcons_game.team_y_score == 14


def test_recap_text_collects_bare_text_and_stops_at_boxscore_image():
    games, _ = parse_games(_FIXTURE_HTML)
    falcons_game = games[0]
    assert "Michael Penix Jr." in falcons_game.recap_text
    assert "Packers turned this opportunity" in falcons_game.recap_text
    assert "nflbox" not in falcons_game.recap_text
    # Doesn't bleed into the next game's own recap text.
    assert "Seahawks were eight-point favorites" not in falcons_game.recap_text


def test_recap_text_never_includes_the_closing_transition():
    games, _ = parse_games(_FIXTURE_HTML)
    for game in games:
        assert "For more thoughts" not in game.recap_text
        assert "NFL Picks" not in game.recap_text


def test_bulleted_byline_recap_preserved_as_bullets():
    games, _ = parse_games(_FIXTURE_HTML)
    jaguars_game = games[2]
    assert "By Charlie Campbell" in jaguars_game.recap_text
    assert "- EDITOR'S NOTE: Drake Maye just keeps getting worse." in jaguars_game.recap_text
    assert "- The Jaguars controlled this game from start to finish." in jaguars_game.recap_text


def test_legacy_nickname_resolves_to_current_abbreviation():
    games, _ = parse_games(_FIXTURE_HTML)
    redskins_game = games[1]
    assert redskins_game.team_x == "WAS"
    assert redskins_game.team_y == "SEA"


def test_normal_nickname_resolves_via_reversed_team_names_table():
    games, _ = parse_games(_FIXTURE_HTML)
    assert games[0].team_x == "ATL"
    assert games[0].team_y == "GB"


def test_unresolved_team_name_kept_verbatim_with_message():
    games, messages = parse_games(_FIXTURE_HTML)
    dragons_game = games[3]
    assert dragons_game.team_x == "LV"  # Raiders resolves fine
    assert dragons_game.team_y == "Dragons"  # unresolved, kept verbatim
    assert any("Dragons" in m for m in messages)


def test_team_name_with_digits_does_not_drop_the_whole_game():
    # "49ers" has digits in it -- confirmed live, a game score-line regex
    # that only allowed letters never matched this team's own score line
    # at all, silently dropping the ENTIRE San Francisco game from
    # parse_games' output (not just its score). This is the regression
    # test for that fix (see _SCORE_LINE_RE's own comment).
    games, messages = parse_games(_FIXTURE_HTML)
    niners_game = games[4]
    assert niners_game.team_x_name == "49ers"
    assert niners_game.team_x_score == 36
    assert niners_game.team_y_name == "Cardinals"
    assert niners_game.team_y_score == 30
    assert niners_game.team_x == "SF"
    assert niners_game.team_y == "ARI"
    assert "Nick Bosa" in niners_game.recap_text
    assert not any("49ers" in m and "Unrecognized" in m for m in messages)


def test_resolve_team_abbrev_case_and_whitespace_insensitive():
    assert resolve_team_abbrev(" falcons ") == "ATL"
    assert resolve_team_abbrev("FALCONS") == "ATL"
    assert resolve_team_abbrev("Not A Team") is None


def test_no_score_lines_found_reports_message():
    games, messages = parse_games("<html><body><p>Nothing here.</p></body></html>")
    assert games == []
    assert any("No game score lines found" in m for m in messages)


def test_page_matches_week_true_for_matching_title():
    assert _page_matches_week(_FIXTURE_HTML, season=2026, week=3) is True


def test_page_matches_week_false_for_different_week_or_season():
    assert _page_matches_week(_FIXTURE_HTML, season=2026, week=4) is False
    assert _page_matches_week(_FIXTURE_HTML, season=2025, week=3) is False


# resolve_away_home -- the site's own score-line text order is NOT trusted
# for home/away (see this module's own docstring); these exercise the
# Schedule-file-based resolution scrape() actually relies on.


def test_resolve_away_home_matches_scraped_order_when_schedule_agrees():
    away, home, resolved = resolve_away_home("ATL", "GB", _SCHEDULE_ROWS, week=3)
    assert (away, home, resolved) == ("ATL", "GB", True)


def test_resolve_away_home_flips_order_when_schedule_disagrees():
    # The site's score line put WAS (home) first -- the Schedule file says
    # SEA is actually away, so resolve_away_home must flip the scraped
    # (team_x, team_y) = ("WAS", "SEA") order back to (SEA, WAS).
    away, home, resolved = resolve_away_home("WAS", "SEA", _SCHEDULE_ROWS, week=3)
    assert (away, home, resolved) == ("SEA", "WAS", True)


def test_resolve_away_home_works_from_either_teams_own_row():
    # Same matchup, called with the pair in the opposite order from the
    # test above -- still resolves correctly regardless of which side's
    # own schedule row ends up being the one that matches.
    away, home, resolved = resolve_away_home("JAX", "NE", _SCHEDULE_ROWS, week=3)
    assert (away, home, resolved) == ("NE", "JAX", True)


def test_resolve_away_home_falls_back_to_scraped_order_when_unresolved():
    away, home, resolved = resolve_away_home("LV", "Dragons", _SCHEDULE_ROWS, week=3)
    assert (away, home, resolved) == ("LV", "Dragons", False)


def test_resolve_away_home_flips_order_for_team_name_with_digits():
    # The site's score line put SF (home) first for the 49ers game too --
    # same flip as the SEA/WAS case, exercised separately here since it's
    # the matchup that triggered the digit-in-nickname regex fix.
    away, home, resolved = resolve_away_home("SF", "ARI", _SCHEDULE_ROWS, week=3)
    assert (away, home, resolved) == ("ARI", "SF", True)


def test_resolve_away_home_falls_back_when_schedule_not_loaded():
    away, home, resolved = resolve_away_home("ATL", "GB", [], week=3)
    assert (away, home, resolved) == ("ATL", "GB", False)


# scrape()'s own url_mode handling -- "auto" (the original numbered-then-
# bare fallback), vs. the two explicit modes the Settings panel's radio
# buttons now let the person force (see game_recap_scraper.py's own
# scrape() docstring). fetch_html and load_schedule_csv are mocked so
# these don't hit the network -- load_schedule_csv returns None (no
# Schedule file) throughout, since away/home resolution isn't what these
# tests are checking.
_ONE_GAME_HTML = """
<html><head><title>NFL Game Recaps: Week 3, 2026 - WalterFootball</title></head>
<body>
<div id="202603___:ATL~GB">
<img src="falconsb_logo.gif"> <img src="packersb_logo.gif">
<br>
<b> Falcons 35, Packers 14 </b> <br>
A short recap.<br> <br>
<img src="images/fball/nflbox2026_082.jpg">
<br> <br>
</div>
</body></html>
"""


class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


def test_scrape_auto_mode_uses_numbered_url_when_available():
    with mock.patch.object(mod, "fetch_html", return_value=_FakeResponse(200, _ONE_GAME_HTML)) as fetch_mock, mock.patch.object(
        mod, "load_schedule_csv", return_value=None
    ):
        games, messages, source_url = scrape(2026, 3)
    assert source_url == mod.build_recap_url(2026, 3)
    assert len(games) == 1
    fetch_mock.assert_called_once_with(mod.build_recap_url(2026, 3))


def test_scrape_auto_mode_falls_back_to_current_url_on_404():
    numbered_response = _FakeResponse(404)
    current_response = _FakeResponse(200, _ONE_GAME_HTML)
    with mock.patch.object(mod, "fetch_html", side_effect=[numbered_response, current_response]), mock.patch.object(
        mod, "load_schedule_csv", return_value=None
    ):
        games, messages, source_url = scrape(2026, 3)
    assert source_url == mod.settings.walterfootball_recap_current_url
    assert len(games) == 1


def test_scrape_week_page_mode_does_not_fall_back_on_404():
    with mock.patch.object(mod, "fetch_html", return_value=_FakeResponse(404)) as fetch_mock, mock.patch.object(
        mod, "load_schedule_csv", return_value=None
    ):
        try:
            scrape(2026, 3, url_mode="week_page")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "isn't available" in str(exc)
    fetch_mock.assert_called_once_with(mod.build_recap_url(2026, 3))


def test_scrape_week_page_mode_succeeds_on_200():
    with mock.patch.object(mod, "fetch_html", return_value=_FakeResponse(200, _ONE_GAME_HTML)), mock.patch.object(
        mod, "load_schedule_csv", return_value=None
    ):
        games, messages, source_url = scrape(2026, 3, url_mode="week_page")
    assert source_url == mod.build_recap_url(2026, 3)
    assert len(games) == 1


def test_scrape_current_page_mode_does_not_try_numbered_url():
    with mock.patch.object(mod, "fetch_html", return_value=_FakeResponse(200, _ONE_GAME_HTML)) as fetch_mock, mock.patch.object(
        mod, "load_schedule_csv", return_value=None
    ):
        games, messages, source_url = scrape(2026, 3, url_mode="current_page")
    assert source_url == mod.settings.walterfootball_recap_current_url
    fetch_mock.assert_called_once_with(mod.settings.walterfootball_recap_current_url)
    assert len(games) == 1


def test_scrape_current_page_mode_raises_on_title_mismatch():
    mismatched_html = _ONE_GAME_HTML.replace("Week 3, 2026", "Week 5, 2026")
    with mock.patch.object(mod, "fetch_html", return_value=_FakeResponse(200, mismatched_html)), mock.patch.object(
        mod, "load_schedule_csv", return_value=None
    ):
        try:
            scrape(2026, 3, url_mode="current_page")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "different week" in str(exc)
