from backend.repositories.contest_results.optimal_lineups_cache_repo import (
    load_top10_by_points,
    save_top10_by_points,
    top10_by_points_path,
)
from backend.schemas.contest_results.contest_results import OptimalLineup, OptimalLineupPlayer


def _make_lineup(total_fpts: float) -> OptimalLineup:
    return OptimalLineup(
        players=[
            OptimalLineupPlayer(roster_position="QB", player="QB A", position="QB", salary=5000, fpts=total_fpts)
        ],
        total_salary=5000,
        total_fpts=total_fpts,
        salary_leftover=45000,
    )


def test_top10_by_points_path_matches_naming_convention(tmp_path):
    path = top10_by_points_path(tmp_path, 2026, 1, "DraftKings", "Classic Main")
    assert path == tmp_path / "2026" / "dk_contest_optimal_lineups_classic_main_week1.json"


def test_load_top10_by_points_returns_none_when_not_generated_yet(tmp_path):
    assert load_top10_by_points(tmp_path, 2026, 1, "DraftKings", "Classic Main") is None


def test_save_and_load_top10_by_points_round_trips(tmp_path):
    lineups = [_make_lineup(100.0), _make_lineup(90.0)]
    save_top10_by_points(tmp_path, 2026, 1, "DraftKings", "Classic Main", lineups)

    loaded = load_top10_by_points(tmp_path, 2026, 1, "DraftKings", "Classic Main")
    assert loaded == lineups


def test_save_overwrites_previous_generation(tmp_path):
    save_top10_by_points(tmp_path, 2026, 1, "DraftKings", "Classic Main", [_make_lineup(1.0)])
    save_top10_by_points(tmp_path, 2026, 1, "DraftKings", "Classic Main", [_make_lineup(2.0), _make_lineup(3.0)])

    loaded = load_top10_by_points(tmp_path, 2026, 1, "DraftKings", "Classic Main")
    assert loaded is not None
    assert [lu.total_fpts for lu in loaded] == [2.0, 3.0]


def test_different_weeks_and_contests_get_separate_files(tmp_path):
    save_top10_by_points(tmp_path, 2026, 1, "DraftKings", "Classic Main", [_make_lineup(1.0)])
    save_top10_by_points(tmp_path, 2026, 2, "DraftKings", "Classic Main", [_make_lineup(2.0)])
    save_top10_by_points(tmp_path, 2026, 1, "DraftKings", "All Games", [_make_lineup(3.0)])

    week1_classic = load_top10_by_points(tmp_path, 2026, 1, "DraftKings", "Classic Main")
    week2_classic = load_top10_by_points(tmp_path, 2026, 2, "DraftKings", "Classic Main")
    week1_all_games = load_top10_by_points(tmp_path, 2026, 1, "DraftKings", "All Games")
    assert week1_classic is not None and week1_classic[0].total_fpts == 1.0
    assert week2_classic is not None and week2_classic[0].total_fpts == 2.0
    assert week1_all_games is not None and week1_all_games[0].total_fpts == 3.0
