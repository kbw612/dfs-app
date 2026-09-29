from pathlib import Path

import csv
import io

from backend.repositories.dk_players.weekly_stats_repo import (
    load_weekly_stats_csv,
    merge_week_into_season_csv,
    week_has_data,
    weekly_stats_csv_path,
    write_usage_share_columns,
)

WEEK1_QB = "RK,NAME,TEAM,POS,WK,OPP,FPTS\n1,Josh Allen,BUF,QB,1,BAL,38.8\n2,Justin Fields,NYJ,QB,1,PIT,29.5\n"
WEEK2_QB = "RK,NAME,TEAM,POS,WK,OPP,FPTS\n1,Patrick Mahomes,KC,QB,2,CIN,31.0\n"
WEEK1_QB_REVISED = "RK,NAME,TEAM,POS,WK,OPP,FPTS\n1,Josh Allen,BUF,QB,1,BAL,40.0\n"


def test_filename_has_no_week_in_it(tmp_path: Path):
    assert weekly_stats_csv_path(tmp_path, 2026, "QB") == tmp_path / "2026" / "FantasyData_QBs.csv"
    assert weekly_stats_csv_path(tmp_path, 2026, "RB") == tmp_path / "2026" / "FantasyData_RBs.csv"
    assert weekly_stats_csv_path(tmp_path, 2026, "WR") == tmp_path / "2026" / "FantasyData_WRs.csv"
    assert weekly_stats_csv_path(tmp_path, 2026, "TE") == tmp_path / "2026" / "FantasyData_TEs.csv"
    assert weekly_stats_csv_path(tmp_path, 2026, "DST") == tmp_path / "2026" / "FantasyData_DSTs.csv"


def test_load_returns_none_when_nothing_saved_yet(tmp_path: Path):
    assert load_weekly_stats_csv(tmp_path, 2026, "QB") is None


def test_merge_first_week_creates_season_file(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    csv_text = load_weekly_stats_csv(tmp_path, 2026, "QB")
    assert csv_text is not None
    assert "Josh Allen" in csv_text
    assert "Justin Fields" in csv_text


def test_merge_second_week_appends_without_touching_first(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    merge_week_into_season_csv(tmp_path, 2026, "QB", 2, WEEK2_QB)
    csv_text = load_weekly_stats_csv(tmp_path, 2026, "QB")
    assert "Josh Allen" in csv_text
    assert "Patrick Mahomes" in csv_text
    assert len(csv_text.strip().splitlines()) == 4  # header + 2 week-1 rows + 1 week-2 row


def test_merge_same_week_again_replaces_only_that_week(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    merge_week_into_season_csv(tmp_path, 2026, "QB", 2, WEEK2_QB)
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB_REVISED)
    csv_text = load_weekly_stats_csv(tmp_path, 2026, "QB")
    assert "Justin Fields" not in csv_text  # old week 1 row replaced
    assert "40.0" in csv_text  # revised week 1 row present
    assert "Patrick Mahomes" in csv_text  # week 2 untouched


def test_week_has_data_false_before_any_save(tmp_path: Path):
    assert week_has_data(tmp_path, 2026, "QB", 1) is False


def test_week_has_data_true_only_for_saved_week(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    assert week_has_data(tmp_path, 2026, "QB", 1) is True
    assert week_has_data(tmp_path, 2026, "QB", 2) is False


def test_merge_keeps_rows_sorted_by_week_then_rank(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 2, WEEK2_QB)
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    csv_text = load_weekly_stats_csv(tmp_path, 2026, "QB")
    lines = csv_text.strip().splitlines()
    # header, then week 1's two rows, then week 2's row
    assert "Josh Allen" in lines[1]
    assert "Justin Fields" in lines[2]
    assert "Patrick Mahomes" in lines[3]


def test_different_positions_are_independent_files(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    assert load_weekly_stats_csv(tmp_path, 2026, "RB") is None
    assert weekly_stats_csv_path(tmp_path, 2026, "RB").exists() is False


# -- write_usage_share_columns ------------------------------------------------


def _rows_by_name(csv_text: str) -> dict[str, dict[str, str]]:
    return {row["NAME"]: row for row in csv.DictReader(io.StringIO(csv_text))}


def test_write_usage_share_columns_appends_header_and_writes_values(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    write_usage_share_columns(
        tmp_path, 2026, "QB", 1, {"Josh Allen": (None, 42.5, 30.0), "Justin Fields": (10.0, 20.0, 15.0)}
    )
    csv_text = load_weekly_stats_csv(tmp_path, 2026, "QB")
    header = next(csv.reader(io.StringIO(csv_text)))
    assert "TGT_SHARE" in header
    assert "TOUCH_SHARE" in header
    assert "OPP_SHARE" in header
    rows = _rows_by_name(csv_text)
    assert rows["Josh Allen"]["TGT_SHARE"] == ""
    assert rows["Josh Allen"]["TOUCH_SHARE"] == "42.5"
    assert rows["Josh Allen"]["OPP_SHARE"] == "30.0"
    assert rows["Justin Fields"]["TGT_SHARE"] == "10.0"
    assert rows["Justin Fields"]["TOUCH_SHARE"] == "20.0"
    assert rows["Justin Fields"]["OPP_SHARE"] == "15.0"


def test_write_usage_share_columns_only_touches_matching_week(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    merge_week_into_season_csv(tmp_path, 2026, "QB", 2, WEEK2_QB)
    write_usage_share_columns(
        tmp_path, 2026, "QB", 1, {"Josh Allen": (5.0, 6.0, 7.0), "Justin Fields": (7.0, 8.0, 9.0)}
    )
    csv_text = load_weekly_stats_csv(tmp_path, 2026, "QB")
    rows = _rows_by_name(csv_text)
    assert rows["Josh Allen"]["TGT_SHARE"] == "5.0"
    # Week 2's row is untouched -- no shares computed for it yet, so the
    # newly-appended columns are simply blank for it.
    assert rows["Patrick Mahomes"]["TGT_SHARE"] == ""
    assert rows["Patrick Mahomes"]["TOUCH_SHARE"] == ""
    assert rows["Patrick Mahomes"]["OPP_SHARE"] == ""


def test_write_usage_share_columns_missing_player_writes_blank(tmp_path: Path):
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    write_usage_share_columns(tmp_path, 2026, "QB", 1, {"Josh Allen": (5.0, 6.0, 7.0)})
    csv_text = load_weekly_stats_csv(tmp_path, 2026, "QB")
    rows = _rows_by_name(csv_text)
    # Justin Fields has no entry in shares_by_player at all.
    assert rows["Justin Fields"]["TGT_SHARE"] == ""
    assert rows["Justin Fields"]["TOUCH_SHARE"] == ""
    assert rows["Justin Fields"]["OPP_SHARE"] == ""


def test_write_usage_share_columns_no_op_when_file_missing(tmp_path: Path):
    write_usage_share_columns(tmp_path, 2026, "QB", 1, {"Josh Allen": (5.0, 6.0, 7.0)})
    assert load_weekly_stats_csv(tmp_path, 2026, "QB") is None


def test_write_usage_share_columns_reapplies_cleanly_on_rerun(tmp_path: Path):
    # Re-running "Calc Week Points" for the same week should simply
    # overwrite that week's own TGT_SHARE/TOUCH_SHARE/OPP_SHARE values, not duplicate
    # columns.
    merge_week_into_season_csv(tmp_path, 2026, "QB", 1, WEEK1_QB)
    write_usage_share_columns(tmp_path, 2026, "QB", 1, {"Josh Allen": (5.0, 6.0, 7.0)})
    write_usage_share_columns(tmp_path, 2026, "QB", 1, {"Josh Allen": (9.0, 10.0, 11.0)})
    csv_text = load_weekly_stats_csv(tmp_path, 2026, "QB")
    header = next(csv.reader(io.StringIO(csv_text)))
    assert header.count("TGT_SHARE") == 1
    assert header.count("TOUCH_SHARE") == 1
    assert header.count("OPP_SHARE") == 1
    rows = _rows_by_name(csv_text)
    assert rows["Josh Allen"]["TGT_SHARE"] == "9.0"
    assert rows["Josh Allen"]["TOUCH_SHARE"] == "10.0"
    assert rows["Josh Allen"]["OPP_SHARE"] == "11.0"
