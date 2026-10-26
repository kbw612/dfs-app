import numpy as np

from backend.schemas.vegas_lines.vegas_lines import VegasLineGame, VegasLinesSnapshot, VegasLineValues
from backend.services.lineup_analyzer.history_loader import HistoricalPlayer, HistoricalWeek
from backend.services.lineup_analyzer.upside_env import (
    EXTRA_FEATURE_NAMES,
    build_extra_pool,
    extra_feature_matrix,
    parse_proj_ceiling,
    team_lines,
)

CSV = (
    "Player,Team,Position,Opponent,Salary,Proj.,Ceiling,% ownership\n"
    "A QB,AAA,QB,BBB,\"$6,000\",20,30,10%\n"
    "B WR,BBB,WR,AAA,\"$5,000\",10,20,5%\n"
    "BBB Defense,BBB,DST,AAA,\"$3,000\",6,12,5%\n"
)


def _week():
    def p(name, pos, team, opp):
        return HistoricalPlayer(name, pos, team, opp, 5000, None, 1.0, 1.0, 0.0)

    pool = {
        "A QB": p("A QB", "QB", "AAA", "BBB"),
        "B WR": p("B WR", "WR", "BBB", "AAA"),
        "Unlisted WR": p("Unlisted WR", "WR", "AAA", "BBB"),
        "Bs": p("Bs", "DST", "BBB", "AAA"),
    }
    return HistoricalWeek(1, {"AAA", "BBB"}, pool, [], True, [])


def test_parse_proj_ceiling_splits_dst_by_team():
    by_name, by_dst = parse_proj_ceiling(CSV)
    assert by_name["A QB"] == (20.0, 30.0)
    assert by_dst["BBB"] == (6.0, 12.0)


def test_team_lines_both_sides_and_skips_incomplete():
    ok = VegasLineGame(
        away_name="a", home_name="b", away_team="AAA", home_team="BBB", game_key="AAA-BBB", kickoff_label="",
        initial=VegasLineValues(), current=VegasLineValues(over_under=44, home_implied_total=24, away_implied_total=20),
    )
    bad = ok.model_copy(update={"away_team": "CCC", "home_team": "DDD", "current": VegasLineValues(over_under=40)})
    snap = VegasLinesSnapshot(season=1, week=1, initial_scraped_at="", current_scraped_at="", games=[ok, bad])
    lines = team_lines(snap)
    assert lines == {"BBB": (24, 20, 44), "AAA": (20, 24, 44)}


def test_unlisted_player_gets_position_floor_and_features_computed():
    week = _week()
    names = sorted(week.pool)
    lines = {"AAA": (20.0, 24.0, 44.0), "BBB": (24.0, 20.0, 44.0)}
    extra = build_extra_pool(week, names, CSV, lines)
    i = {n: k for k, n in enumerate(names)}
    assert extra.proj[i["Unlisted WR"]] == 10.0  # lowest listed WR
    assert extra.proj[i["Bs"]] == 6.0
    lineup = np.array([[i["A QB"], i["B WR"], i["Unlisted WR"], i["B WR"], i["B WR"], i["B WR"], i["B WR"], i["B WR"], i["Bs"]]])
    x = extra_feature_matrix(lineup, extra)[0]
    f = dict(zip(EXTRA_FEATURE_NAMES, x))
    assert f["qb_game_total"] == 44
    assert f["dst_opp_implied"] == 20.0  # BBB defense faces AAA, implied 20


def test_missing_inputs_zero_the_features():
    week = _week()
    names = sorted(week.pool)
    extra = build_extra_pool(week, names, None, {})
    assert not extra.has_projections and not extra.has_lines
    lineup = np.zeros((2, 9), dtype=int)
    assert not extra_feature_matrix(lineup, extra).any()


def test_slate_signature_changes_when_projections_change(tmp_path, monkeypatch):
    from backend.api import lineup_analyzer as api
    from backend.repositories.ownership.projections_repo import save_projections_csv

    monkeypatch.setattr(api.settings, "nfl_data_dir", tmp_path, raising=False)
    first = api.slate_signature(2026, 1, "DraftKings", "Classic Main")
    save_projections_csv(tmp_path, 2026, 1, "DraftKings", CSV)
    second = api.slate_signature(2026, 1, "DraftKings", "Classic Main")
    save_projections_csv(tmp_path, 2026, 1, "DraftKings", CSV.replace("10%", "11%"))
    third = api.slate_signature(2026, 1, "DraftKings", "Classic Main")
    assert len({first, second, third}) == 3
