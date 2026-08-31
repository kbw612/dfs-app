from pathlib import Path

from backend.repositories.game_environment.game_environment_repo import save_game_environment
from backend.repositories.player_attributes.entries_repo import save_entry as save_attribute_entry
from backend.repositories.player_pool.entries_repo import save_entry
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.player_attributes.player_attributes import PlayerAttributeEntry
from backend.schemas.player_pool.player_pool import PlayerPoolEntry
from backend.services.player_pool.engine import compute_player_pool, entry_total


def make_player(player, position, team, opponent, salary, ownership_pct=None):
    return OwnershipPlayer(
        player=player,
        position=position,
        team=team,
        opponent=opponent,
        is_home=True,
        salary=salary,
        ownership_pct=ownership_pct,
    )


def make_game_env(**overrides) -> GameEnvironmentEntry:
    fields = dict(
        season=2025,
        week=9,
        game_key="BUF-NO",
        home_team="BUF",
        away_team="NO",
        home_spread=-3.5,
        over_under=45.0,
        home_implied_total=27.0,
        away_implied_total=18.0,
    )
    fields.update(overrides)
    return GameEnvironmentEntry(**fields)


def dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """(player_pool_dir, game_environment_dir, player_attributes_dir) --
    all three repos write a file named "entries_{season}.json" (see each
    repo's docstring), so they need separate directories, same as in
    production (backend/config.py's player_pool_dir vs
    game_environment_dir vs player_attributes_dir)."""
    return tmp_path / "player_pool", tmp_path / "game_environment", tmp_path / "player_attributes"


def test_entry_total_sums_only_non_none_fields():
    assert entry_total({"ownership": 3.0, "volume": 2.0, "talent": None}) == 5.0


def test_entry_total_zero_when_nothing_scored():
    assert entry_total({"ownership": None, "volume": None}) == 0.0


def test_compute_player_pool_merges_saved_scores(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_entry(pp_dir, PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=3.0))
    save_attribute_entry(pa_dir, PlayerAttributeEntry(season=2025, week=9, player="Josh Allen", volume=2.0))
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)

    assert len(result.players) == 1
    row = result.players[0]
    assert row.ownership == 3.0
    assert row.volume == 2.0
    # game_matchup (2.0) + game_environment (2.0, no odds data yet) both
    # default to neutral -- 3 (ownership) + 2 (volume) + 2 + 2 = 9.
    assert row.total == 9.0


def test_compute_player_pool_unscored_player_defaults_game_matchup_ownership_environment_to_neutral(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    players = [make_player("Nobody", "WR", "SF", "LAR", 4000)]
    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    # A brand new week with nothing scored yet -- Game Environment,
    # Matchup, and Ownership all start at 2.0 rather than blank; Volume
    # and Talent have no history to carry forward from, so they stay None.
    assert row.game_environment == 2.0
    assert row.game_matchup == 2.0
    assert row.ownership == 2.0
    assert row.volume is None
    assert row.talent is None
    assert row.total == 6.0


def test_compute_player_pool_sorts_by_total_descending(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_attribute_entry(pa_dir, PlayerAttributeEntry(season=2025, week=9, player="Low", talent=1.0))
    save_attribute_entry(pa_dir, PlayerAttributeEntry(season=2025, week=9, player="High", talent=3.0))
    save_entry(pp_dir, PlayerPoolEntry(season=2025, week=9, player="High", ownership=3.0))
    players = [
        make_player("Low", "WR", "SF", "LAR", 4000),
        make_player("High", "WR", "SF", "LAR", 8000),
    ]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    assert [p.player for p in result.players] == ["High", "Low"]


def test_compute_player_pool_carries_forward_volume_and_talent(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_attribute_entry(pa_dir, PlayerAttributeEntry(season=2025, week=8, player="Gibbs", volume=3.0, talent=3.0))
    players = [make_player("Gibbs", "RB", "DET", "GB", 8500)]

    result = compute_player_pool(players, 2025, 10, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    assert row.volume == 3.0
    assert row.talent == 3.0


def test_compute_player_pool_does_not_carry_forward_ownership_or_matchup(tmp_path: Path):
    # Ownership/Game Matchup/Salary Value are expected to be re-entered
    # fresh each week -- only Volume/Talent (a different shared resource,
    # see player_attributes) carry forward. Ownership and Game Matchup
    # still resolve to a value (the 2.0 neutral default), but it's *not*
    # last week's saved 3.0/2.5 -- proving no carry-forward happened, just
    # the flat default kicking in.
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_entry(pp_dir, PlayerPoolEntry(season=2025, week=8, player="Gibbs", ownership=3.0, game_matchup=2.5))
    players = [make_player("Gibbs", "RB", "DET", "GB", 8500)]

    result = compute_player_pool(players, 2025, 10, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    assert row.ownership == 2.0
    assert row.game_matchup == 2.0


def test_compute_player_pool_reflects_this_weeks_explicit_override_over_carry_forward(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_attribute_entry(pa_dir, PlayerAttributeEntry(season=2025, week=8, player="Gibbs", volume=3.0))
    save_attribute_entry(pa_dir, PlayerAttributeEntry(season=2025, week=10, player="Gibbs", volume=1.0))
    players = [make_player("Gibbs", "RB", "DET", "GB", 8500)]

    result = compute_player_pool(players, 2025, 10, pp_dir, ge_dir, pa_dir)
    assert result.players[0].volume == 1.0


def test_compute_player_pool_builds_game_options_from_players(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "ARI", "HOU", 4000),
        make_player("C", "WR", "SF", "LAR", 6000),
    ]
    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    labels = {g.label for g in result.games}
    assert labels == {"ARI vs HOU", "LAR vs SF"}


def test_compute_player_pool_includes_ownership_pct_as_reference(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    players = [make_player("A", "WR", "SF", "LAR", 6000, ownership_pct=12.5)]
    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    assert result.players[0].ownership_pct == 12.5


def test_compute_player_pool_uses_formula_suggestion_when_no_override(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_game_environment(ge_dir, make_game_env(home_implied_total=27.0, away_implied_total=18.0))
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    # BUF's implied total (27.0) is >=24 -> top tier -> 3.0.
    assert row.game_environment_suggested == 3.0
    assert row.game_environment_override is None
    assert row.game_environment == 3.0
    # game_matchup + ownership both default to the neutral 2.0 -- 3 + 2 + 2 = 7.
    assert row.total == 7.0


def test_compute_player_pool_explicit_override_wins_over_suggestion(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_game_environment(ge_dir, make_game_env(home_implied_total=27.0, away_implied_total=18.0))
    save_entry(pp_dir, PlayerPoolEntry(season=2025, week=9, player="Josh Allen", game_environment=1.5))
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    assert row.game_environment_suggested == 3.0
    assert row.game_environment_override == 1.5
    assert row.game_environment == 1.5
    # game_matchup + ownership both default to the neutral 2.0 -- 1.5 + 2 + 2 = 5.5.
    assert row.total == 5.5


def test_compute_player_pool_uses_away_teams_own_implied_total(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_game_environment(ge_dir, make_game_env(home_implied_total=27.0, away_implied_total=18.0))
    players = [make_player("Away Player", "WR", "NO", "BUF", 5000)]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    # NO's implied total (18.0) is <20 -> bottom tier -> 1.0.
    assert row.game_environment_suggested == 1.0
    assert row.game_environment == 1.0


def test_compute_player_pool_defaults_game_environment_to_neutral_without_data(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    assert row.game_environment_suggested == 2.0
    assert row.game_environment == 2.0
    # game_environment + game_matchup + ownership all default to 2.0 -- 6.0.
    assert row.total == 6.0


def test_compute_player_pool_dst_has_no_ownership_or_game_environment(tmp_path: Path):
    # DSTs only ever use Game Matchup + Salary Value -- Ownership and
    # Game Environment shouldn't apply (or default) to them at all, even
    # though those fields default to something for every offensive
    # position. Regression test for a bug where DST rows picked up a
    # phantom Ownership=2.0/Game Environment=2.0 that never showed up in
    # the DST grid but silently inflated the total anyway.
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    players = [make_player("Chargers", "DST", "LAC", "ARI", 3500)]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    assert row.ownership is None
    assert row.game_environment is None
    assert row.game_environment_suggested is None
    assert row.volume is None
    assert row.talent is None
    # Only game_matchup defaults for DST -- salary_value stays unscored.
    assert row.game_matchup == 2.0
    assert row.salary_value is None
    assert row.total == 2.0


def test_compute_player_pool_dst_ignores_saved_player_attributes(tmp_path: Path):
    # Even if Volume/Talent somehow got saved for a DST (e.g. leftover
    # data from a position change), they still shouldn't apply -- the
    # position gate is unconditional, not just "was this ever entered".
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_attribute_entry(pa_dir, PlayerAttributeEntry(season=2025, week=9, player="Chargers", volume=3.0, talent=3.0))
    players = [make_player("Chargers", "DST", "LAC", "ARI", 3500)]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    row = result.players[0]
    assert row.volume is None
    assert row.talent is None


def test_compute_player_pool_returns_saved_game_environment_entries(tmp_path: Path):
    pp_dir, ge_dir, pa_dir = dirs(tmp_path)
    save_game_environment(ge_dir, make_game_env())
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, pp_dir, ge_dir, pa_dir)
    assert len(result.game_environment) == 1
    assert result.game_environment[0].game_key == "BUF-NO"
