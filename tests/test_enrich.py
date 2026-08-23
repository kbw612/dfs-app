from pathlib import Path

import pytest

from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team
from backend.services.depth_charts.enrich import (
    compute_defensive_formation,
    enrich_defensive_formation,
    enrich_team_abbrev,
)


@pytest.fixture
def team_info_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "team-info.csv"
    csv_path.write_text(
        "Team,Full Name,Bye Week,Offensive Tier,Offensive Rank\n"
        "ARI,Arizona Cardinals,8,2,14\n"
        "ATL,Atlanta Falcons,5,1,1\n"
    )
    return csv_path


def make_snapshot(team_names: list[str]) -> Snapshot:
    return Snapshot(
        scraped_at="2026-08-07T08:00:00-04:00",
        source_url="https://example.com",
        teams=[Team(team_name=name, positions={}) for name in team_names],
    )


def test_enrich_team_abbrev_matches_known_teams(team_info_csv: Path):
    snapshot = make_snapshot(["Arizona Cardinals", "Atlanta Falcons"])
    snapshot = enrich_team_abbrev(snapshot, team_info_csv)

    assert snapshot.teams[0].team_abbrev == "ARI"
    assert snapshot.teams[1].team_abbrev == "ATL"
    assert not any(m.level == "error" for m in snapshot.messages)


def test_enrich_team_abbrev_logs_error_on_mismatch(team_info_csv: Path):
    snapshot = make_snapshot(["St. Louis Rams"])
    snapshot = enrich_team_abbrev(snapshot, team_info_csv)

    assert snapshot.teams[0].team_abbrev is None
    error_messages = [m for m in snapshot.messages if m.level == "error"]
    assert len(error_messages) == 1
    assert "St. Louis Rams" in error_messages[0].message
    assert error_messages[0].step == "enrich_team_abbrev"


def test_enrich_team_abbrev_continues_after_one_mismatch(team_info_csv: Path):
    """Partial failure handling per the design doc: one bad match doesn't
    block the rest of the run."""
    snapshot = make_snapshot(["Arizona Cardinals", "St. Louis Rams", "Atlanta Falcons"])
    snapshot = enrich_team_abbrev(snapshot, team_info_csv)

    assert snapshot.teams[0].team_abbrev == "ARI"
    assert snapshot.teams[1].team_abbrev is None
    assert snapshot.teams[2].team_abbrev == "ATL"


def test_compute_defensive_formation_4_3_when_mlb_present():
    positions = {"MLB": [Player(player="Mack Wilson")], "NT": []}
    assert compute_defensive_formation(positions) == "4-3"


def test_compute_defensive_formation_3_4_when_nt_present():
    positions = {"MLB": [], "NT": [Player(player="Da'Shawn Hand")]}
    assert compute_defensive_formation(positions) == "3-4"


def test_compute_defensive_formation_null_when_neither_present():
    positions = {"MLB": [], "NT": []}
    assert compute_defensive_formation(positions) is None


def test_enrich_defensive_formation_logs_warning_when_null():
    snapshot = make_snapshot(["Miami Dolphins"])
    snapshot.teams[0].positions = {"MLB": [], "NT": []}
    snapshot = enrich_defensive_formation(snapshot)

    assert snapshot.teams[0].defensive_formation is None
    warnings = [m for m in snapshot.messages if m.level == "warning"]
    assert len(warnings) == 1
    assert "Miami Dolphins" in warnings[0].message
