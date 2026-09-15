import csv
import io
from pathlib import Path
from unittest import mock

from backend.config import settings
from backend.services.ownership import main_slate_scraper as mod
from backend.services.ownership.csv_loader import parse_ownership_projections_csv
from backend.services.ownership.main_slate_scraper import extract_displayed_week, parse_main_slate_csv, scrape_main_slate

FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "sample_main_slate.html").read_text()
NO_TABLE_HTML = "<div>Please log in to view this page</div>"


def test_extract_displayed_week_finds_week_label():
    assert extract_displayed_week(FIXTURE_HTML) == 1


def test_extract_displayed_week_none_when_no_label_present():
    assert extract_displayed_week("<div>nothing here</div>") is None


def test_parse_main_slate_csv_reads_only_the_all_positions_table():
    csv_text, _ = parse_main_slate_csv(FIXTURE_HTML)
    assert csv_text is not None
    assert "Should Not Be Scraped" not in csv_text
    assert "Jahmyr Gibbs" in csv_text
    assert "Puka Nacua" in csv_text


def test_parse_main_slate_csv_renames_headers_for_parser_compatibility():
    csv_text, _ = parse_main_slate_csv(FIXTURE_HTML)
    header = next(csv.reader(io.StringIO(csv_text)))
    assert header == ["Player", "Team", "Position", "Opponent", "Salary", "Proj.", "Ceiling", "% ownership", "Tm Own"]


def test_parse_main_slate_csv_normalizes_la_team_abbreviations():
    csv_text, _ = parse_main_slate_csv(FIXTURE_HTML)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    puka = next(r for r in rows if r["Player"] == "Puka Nacua")
    # Site renders the Rams as "LA" and the Chargers as "LARC" -- both get
    # fixed to this app's own abbreviations (see parsing.py's docstring).
    assert puka["Team"] == "LAR"
    assert puka["Opponent"] == "LAC"


def test_parse_main_slate_csv_output_parses_cleanly_with_existing_loader():
    csv_text, _ = parse_main_slate_csv(FIXTURE_HTML)
    players, messages = parse_ownership_projections_csv(csv_text)
    assert len(players) == 3
    gibbs = next(p for p in players if p.player == "Jahmyr Gibbs")
    assert gibbs.ownership_pct == 44.59
    assert gibbs.salary == 8000
    assert gibbs.team == "DET"
    assert gibbs.opponent == "NO"
    no_own = next(p for p in players if p.player == "No Own Player")
    assert no_own.ownership_pct is None
    assert messages == []


def test_parse_main_slate_csv_missing_table_reports_error():
    csv_text, messages = parse_main_slate_csv("<div>no tables here</div>")
    assert csv_text is None
    assert any("all-positions table" in m.message for m in messages)
    assert messages[0].level == "error"


def test_build_session_skips_login_when_no_credentials_configured(monkeypatch):
    monkeypatch.setattr(settings, "ownership_source_username", None)
    monkeypatch.setattr(settings, "ownership_source_password", None)
    with mock.patch.object(mod, "login") as login_mock:
        session = mod.build_session()
    login_mock.assert_not_called()
    assert session is not None


def test_build_session_logs_in_when_credentials_configured(monkeypatch):
    monkeypatch.setattr(settings, "ownership_source_username", "me@example.com")
    monkeypatch.setattr(settings, "ownership_source_password", "hunter2")
    with mock.patch.object(mod, "login") as login_mock:
        session = mod.build_session()
    login_mock.assert_called_once_with(session, settings.ownership_source_url, "me@example.com", "hunter2")


def test_scrape_main_slate_success_end_to_end(monkeypatch):
    monkeypatch.setattr(settings, "ownership_source_username", None)
    monkeypatch.setattr(settings, "ownership_source_password", None)
    with mock.patch.object(mod, "fetch_main_slate_html", return_value=FIXTURE_HTML):
        csv_text, displayed_week, messages = scrape_main_slate("https://oneweekseason.com/draftkings-main-slate/")
    assert csv_text is not None
    assert displayed_week == 1
    assert not any(m.level == "error" for m in messages)


def test_scrape_main_slate_missing_table_hints_to_set_credentials_when_none_configured(monkeypatch):
    monkeypatch.setattr(settings, "ownership_source_username", None)
    monkeypatch.setattr(settings, "ownership_source_password", None)
    with mock.patch.object(mod, "fetch_main_slate_html", return_value=NO_TABLE_HTML):
        csv_text, _, messages = scrape_main_slate("https://oneweekseason.com/draftkings-main-slate/")
    assert csv_text is None
    assert any("DFS_APP_OWNERSHIP_SOURCE_USERNAME" in m.message for m in messages)


def test_scrape_main_slate_missing_table_hints_at_bad_credentials_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "ownership_source_username", "me@example.com")
    monkeypatch.setattr(settings, "ownership_source_password", "hunter2")
    with mock.patch.object(mod, "login"):
        with mock.patch.object(mod, "fetch_main_slate_html", return_value=NO_TABLE_HTML):
            csv_text, _, messages = scrape_main_slate("https://oneweekseason.com/draftkings-main-slate/")
    assert csv_text is None
    assert any("Logged in with the configured OWS credentials" in m.message for m in messages)
