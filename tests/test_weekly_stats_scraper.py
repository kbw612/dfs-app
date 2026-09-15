import csv
import io
from pathlib import Path
from unittest import mock

import pytest

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
