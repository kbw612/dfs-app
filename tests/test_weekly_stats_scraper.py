import csv
import io
from pathlib import Path
from unittest import mock

import pytest
from bs4 import BeautifulSoup

from backend.services.dk_players import weekly_stats_scraper as mod
from backend.services.dk_players.weekly_stats_scraper import (
    WeeklyStatsScrapeError,
    parse_weekly_stats_html,
    scrape_weekly_stats_csv,
)

FIXTURES = Path(__file__).parent / "fixtures"
QB_HTML = (FIXTURES / "sample_fantasydata_qb.html").read_text()
RB_HTML = (FIXTURES / "sample_fantasydata_rb.html").read_text()
WR_HTML = (FIXTURES / "sample_fantasydata_wr.html").read_text()
DST_HTML = (FIXTURES / "sample_fantasydata_dst.html").read_text()
NO_TABLE_HTML = "<div>nothing here</div>"


def test_parse_qb_html_produces_expected_header_and_rows():
    csv_text = parse_weekly_stats_html(QB_HTML, "QB")
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0] == [
        "RK", "NAME", "TEAM", "POS", "WK", "OPP",
        "PASSING_CMP", "PASSING_ATT", "PASSING_CMP%", "PASSING_YDS", "PASSING_AVG",
        "PASSING_TD", "INT", "LONG", "SCK", "RATING",
        "RUSHING_ATT", "RUSHING_YDS", "RUSHING_AVG", "RUSHING_TD", "FPTS",
    ]
    assert len(rows) == 3  # header + 2 players
    allen = next(r for r in csv.DictReader(io.StringIO(csv_text)) if r["NAME"] == "Josh Allen")
    assert allen["TEAM"] == "BUF"
    assert allen["PASSING_TD"] == "2"
    assert allen["FPTS"] == "38.8"


def test_parse_rb_html_produces_expected_header_and_rows():
    csv_text = parse_weekly_stats_html(RB_HTML, "RB")
    header = next(csv.reader(io.StringIO(csv_text)))
    assert header == [
        "RK", "NAME", "TEAM", "POS", "WK", "OPP",
        "RUSHING_ATT", "RUSHING_YDS", "RUSHING_AVG", "RUSHING_TD",
        "RECEIVING_TGTS", "RECEIVING_REC", "RECEIVING_YDS", "RECEIVING_TD",
        "FUMBLES", "FUMBLES_LOST", "FPTS",
    ]
    henry = next(r for r in csv.DictReader(io.StringIO(csv_text)) if r["NAME"] == "Derrick Henry")
    assert henry["RUSHING_YDS"] == "169"
    assert henry["FPTS"] == "29.7"


def test_parse_wr_html_produces_expected_header_and_rows():
    csv_text = parse_weekly_stats_html(WR_HTML, "WR")
    header = next(csv.reader(io.StringIO(csv_text)))
    assert header == [
        "RK", "NAME", "TEAM", "POS", "WK", "OPP",
        "RECEIVING_TGTS", "RECEIVING_REC", "CATCH%", "RECEIVING_YDS", "RECEIVING_TD", "LONG",
        "YDS/TGT", "YDS/REC", "RUSHING_ATT", "RUSHING_YDS", "RUSHING_AVG", "RUSHING_TD",
        "FUMBLES", "FUMBLES_LOST", "FPTS",
    ]
    nacua = next(r for r in csv.DictReader(io.StringIO(csv_text)) if r["NAME"] == "Puka Nacua")
    assert nacua["RECEIVING_YDS"] == "130"


def test_parse_te_html_uses_same_column_set_as_wr():
    # TE renders an identical data-id list to WR on the real site -- the
    # WR fixture doubles as the TE fixture here for exactly that reason.
    csv_text = parse_weekly_stats_html(WR_HTML, "TE")
    header = next(csv.reader(io.StringIO(csv_text)))
    assert "RECEIVING_TGTS" in header
    assert "CATCH%" in header


def test_parse_dst_html_synthesizes_rk_name_pos_and_disambiguated_columns():
    csv_text = parse_weekly_stats_html(DST_HTML, "DST")
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0] == [
        "RK", "NAME", "TEAM", "POS", "WK", "OPP", "LOSS", "DEF_SCK", "QB_HITS",
        "DEF_INT", "FR", "SFTY", "DEF_TD", "RET_TD", "OPP_PTS", "FPTS",
    ]
    assert len(rows) == 3  # header + 2 defenses

    chargers = next(r for r in csv.DictReader(io.StringIO(csv_text)) if r["TEAM"] == "LAC")
    assert chargers["RK"] == "1"
    assert chargers["NAME"] == "Chargers"  # converted from TEAM via resolve_team_nickname
    assert chargers["POS"] == "DST"
    assert chargers["WK"] == "3"
    assert chargers["OPP"] == "DEN"
    assert chargers["LOSS"] == "7"
    assert chargers["DEF_SCK"] == "4"
    assert chargers["QB_HITS"] == "9"
    assert chargers["DEF_INT"] == "2"
    assert chargers["FR"] == "1"
    assert chargers["SFTY"] == "0"
    assert chargers["DEF_TD"] == "1"
    assert chargers["RET_TD"] == "0"
    assert chargers["OPP_PTS"] == "10"
    assert chargers["FPTS"] == "17.0"

    cowboys = next(r for r in csv.DictReader(io.StringIO(csv_text)) if r["TEAM"] == "DAL")
    assert cowboys["RK"] == "2"  # second row in the (already FPTS-sorted) table
    assert cowboys["NAME"] == "Cowboys"


def test_parse_dst_html_falls_back_to_raw_text_for_unresolved_team_full_name():
    # An unrecognized full-name string (site rename/typo, or a fixture
    # that doesn't match config/team-info.csv's own "Full Name" spelling)
    # falls back to using that raw text as-is for both TEAM and NAME,
    # rather than failing the whole scrape.
    unresolved_html = DST_HTML.replace(">Los Angeles Chargers<", ">Some Unknown Team<")
    csv_text = parse_weekly_stats_html(unresolved_html, "DST")
    row = next(r for r in csv.DictReader(io.StringIO(csv_text)) if r["TEAM"] == "Some Unknown Team")
    assert row["NAME"] == "Some Unknown Team"


def test_parse_dst_html_converts_full_team_name_to_abbreviation_in_team_column():
    # DST's own TEAM cell renders the full team name as link text (unlike
    # every other position's plain abbreviation) -- this is the exact
    # real-world case that silently produced garbage NAME/TEAM values
    # before team_abbrev_by_full_name was added.
    csv_text = parse_weekly_stats_html(DST_HTML, "DST")
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert {r["TEAM"] for r in rows} == {"LAC", "DAL"}
    assert "Los Angeles Chargers" not in csv_text
    assert "Dallas Cowboys" not in csv_text


def test_parse_dst_html_works_with_single_row_thead():
    # DST's real page has no PASSING/RUSHING/RECEIVING-style group-label row,
    # so its <thead> holds exactly one <tr> -- unlike QB/RB/WR/TE, which have
    # two. This is a regression test for a bug where the parser hardcoded
    # header_rows[1] and `len(header_rows) < 2`, which raised
    # WeeklyStatsScrapeError on every real DST scrape.
    thead = BeautifulSoup(DST_HTML, "html.parser").select_one("table.stats thead")
    assert len(thead.select("tr")) == 1
    csv_text = parse_weekly_stats_html(DST_HTML, "DST")
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert len(rows) == 3  # header + 2 defenses


def test_parse_qb_html_still_works_with_two_row_thead():
    # QB/RB/WR/TE's group-label row above the real header row must still be
    # skipped correctly (header_rows[-1], not header_rows[0]).
    thead = BeautifulSoup(QB_HTML, "html.parser").select_one("table.stats thead")
    assert len(thead.select("tr")) == 2
    csv_text = parse_weekly_stats_html(QB_HTML, "QB")
    assert "Josh Allen" in csv_text


def test_parse_missing_table_raises():
    with pytest.raises(WeeklyStatsScrapeError, match="stats table"):
        parse_weekly_stats_html(NO_TABLE_HTML, "QB")


def test_parse_missing_expected_column_raises():
    # A QB page missing pass_rating's data-id (site markup changed).
    broken = QB_HTML.replace('data-id="pass_rating"', "")
    with pytest.raises(WeeklyStatsScrapeError, match="missing expected column"):
        parse_weekly_stats_html(broken, "QB")


def test_build_url_includes_expected_query_params():
    url = mod._build_url(2026, 1, "RB")
    assert "sp=2026_REG" in url
    assert "week_from=1" in url
    assert "week_to=1" in url
    assert "position=rb" in url


def test_scrape_weekly_stats_csv_fetches_then_parses(monkeypatch):
    with mock.patch.object(mod, "fetch_weekly_stats_html", return_value=QB_HTML) as fetch_mock:
        csv_text = scrape_weekly_stats_csv(2026, 1, "QB")
    fetch_mock.assert_called_once_with(2026, 1, "QB")
    assert "Josh Allen" in csv_text
