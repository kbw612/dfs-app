from pathlib import Path

from backend.repositories.game_environment.game_environment_repo import save_game_environment
from backend.repositories.player_defaults.defaults_repo import save_default
from backend.repositories.player_pool.entries_repo import save_entry
from backend.schemas.game_environment.game_environment import GameEnvironmentEntry
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.player_defaults.player_defaults import PlayerDefaultEntry
from backend.schemas.player_pool.player_pool import PlayerPoolEntry
from backend.services.player_pool.engine import compute_player_pool, entry_total


def make_player(player, position, team, opponent, salary, ownership_pct=None, depth_rank=None):
    return OwnershipPlayer(
        player=player,
        position=position,
        team=team,
        opponent=opponent,
        is_home=True,
        salary=salary,
        ownership_pct=ownership_pct,
        depth_rank=depth_rank,
    )


def make_game_env(**overrides) -> GameEnvironmentEntry:
    fields = dict(
        season=2025,
        week=9,
        game_key="BUF-NO",
        home_team="BUF",
        away_team="NO",
        over_under=45.0,
        home_implied_total=27.0,
        away_implied_total=18.0,
    )
    fields.update(overrides)
    return GameEnvironmentEntry(**fields)


PLATFORM = "DraftKings"


def dirs(tmp_path: Path) -> tuple[Path, Path]:
    """(game_environment_dir, nfl_data_dir) -- separate roots so each
    repo's own on-disk file doesn't collide with the others, same as in
    production (backend/config.py's game_environment_dir vs nfl_data_dir).
    Player Pool's own per-week entries and Player Defaults' per-season
    Default both live under nfl_data_dir now (see repositories/
    player_pool/entries_repo.py and repositories/player_defaults/
    defaults_repo.py)."""
    return tmp_path / "game_environment", tmp_path / "nfl_data"


def test_entry_total_sums_only_non_none_fields():
    assert entry_total({"ownership": 3.0, "volume": 2.0, "talent": None}) == 5.0


def test_entry_total_zero_when_nothing_scored():
    assert entry_total({"ownership": None, "volume": None}) == 0.0


def test_compute_player_pool_passes_through_depth_rank(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Joe Mixon", "RB", "HOU", "ARI", 6800, depth_rank=1)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)

    assert result.players[0].depth_rank == 1


def test_compute_player_pool_depth_rank_none_when_unmatched(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Some Backup", "RB", "HOU", "ARI", 4200)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)

    assert result.players[0].depth_rank is None


def test_compute_player_pool_merges_saved_scores(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    save_entry(nfl_dir, PlayerPoolEntry(season=2025, week=9, player="Josh Allen", ownership=3.0, volume=2.0))
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)

    assert len(result.players) == 1
    row = result.players[0]
    assert row.ownership == 3.0
    assert row.volume == 2.0
    # game_matchup and talent (no explicit save or Default) default to the
    # neutral 2.0; game_environment (no odds data yet) defaults to its own
    # neutral 0.5 -- 3 (ownership) + 2 (volume) + 2 (game_matchup) +
    # 2 (talent) + 0.5 (game_environment) = 9.5.
    assert row.total == 9.5


def test_compute_player_pool_unscored_player_defaults_everything_to_neutral(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Nobody", "WR", "SF", "LAR", 4000)]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    # A brand new week with nothing scored yet and no Player Default set
    # either -- every applicable field starts at its own neutral value
    # rather than blank (2.0 for the 1.0-3.0 fields, 0.5 for
    # game_environment's own 0.0-1.0 scale).
    assert row.game_environment == 0.5
    assert row.game_matchup == 2.0
    assert row.ownership == 2.0
    assert row.volume == 2.0
    assert row.talent == 2.0
    assert row.total == 8.5


def test_compute_player_pool_sorts_by_total_descending(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    save_entry(nfl_dir, PlayerPoolEntry(season=2025, week=9, player="Low", talent=1.0))
    save_entry(nfl_dir, PlayerPoolEntry(season=2025, week=9, player="High", ownership=3.0, talent=3.0))
    players = [
        make_player("Low", "WR", "SF", "LAR", 4000),
        make_player("High", "WR", "SF", "LAR", 8000),
    ]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    assert [p.player for p in result.players] == ["High", "Low"]


def test_compute_player_pool_falls_back_to_default_when_week_unscored(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    save_default(nfl_dir, PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0, talent=3.0))
    players = [make_player("Gibbs", "RB", "DET", "GB", 8500)]

    result = compute_player_pool(players, 2025, 10, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    assert row.volume == 3.0
    assert row.talent == 3.0


def test_compute_player_pool_this_weeks_explicit_value_wins_over_default(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    save_default(nfl_dir, PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0))
    save_entry(nfl_dir, PlayerPoolEntry(season=2025, week=10, player="Gibbs", volume=1.0))
    players = [make_player("Gibbs", "RB", "DET", "GB", 8500)]

    result = compute_player_pool(players, 2025, 10, PLATFORM, ge_dir, nfl_dir)
    assert result.players[0].volume == 1.0


def test_compute_player_pool_does_not_carry_forward_volume_or_talent_from_earlier_week(tmp_path: Path):
    # An explicit save for an earlier week (week 8) should have zero effect
    # on a later week (week 10) that has neither its own explicit save nor
    # a Player Default -- unlike the old carry-forward design, week 10
    # falls straight to the neutral 2.0, not week 8's 3.0.
    ge_dir, nfl_dir = dirs(tmp_path)
    save_entry(nfl_dir, PlayerPoolEntry(season=2025, week=8, player="Gibbs", volume=3.0, talent=3.0))
    players = [make_player("Gibbs", "RB", "DET", "GB", 8500)]

    result = compute_player_pool(players, 2025, 10, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    assert row.volume == 2.0
    assert row.talent == 2.0


def test_compute_player_pool_does_not_carry_forward_ownership_or_matchup(tmp_path: Path):
    # Ownership/Game Matchup/Salary Value are expected to be re-entered
    # fresh each week and have no Player Default fallback the way
    # Volume/Talent do. They still resolve to a value (the 2.0 neutral
    # default), but it's *not* last week's saved 3.0/2.5 -- proving no
    # carry-forward happened, just the flat default kicking in.
    ge_dir, nfl_dir = dirs(tmp_path)
    save_entry(nfl_dir, PlayerPoolEntry(season=2025, week=8, player="Gibbs", ownership=3.0, game_matchup=2.5))
    players = [make_player("Gibbs", "RB", "DET", "GB", 8500)]

    result = compute_player_pool(players, 2025, 10, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    assert row.ownership == 2.0
    assert row.game_matchup == 2.0


def test_compute_player_pool_setting_default_does_not_touch_already_saved_week(tmp_path: Path):
    # Saving/changing a Player Default is purely a fallback for weeks
    # without their own explicit save -- it never rewrites a week that's
    # already been explicitly scored.
    ge_dir, nfl_dir = dirs(tmp_path)
    save_entry(nfl_dir, PlayerPoolEntry(season=2025, week=9, player="Gibbs", volume=1.0))
    save_default(nfl_dir, PlayerDefaultEntry(season=2025, player="Gibbs", volume=3.0))

    result = compute_player_pool(
        [make_player("Gibbs", "RB", "DET", "GB", 8500)], 2025, 9, PLATFORM, ge_dir, nfl_dir
    )
    assert result.players[0].volume == 1.0


def test_compute_player_pool_builds_game_options_from_players(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "ARI", "HOU", 4000),
        make_player("C", "WR", "SF", "LAR", 6000),
    ]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    labels = {g.label for g in result.games}
    assert labels == {"ARI vs HOU", "LAR vs SF"}


def test_compute_player_pool_includes_ownership_pct_as_reference(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("A", "WR", "SF", "LAR", 6000, ownership_pct=12.5)]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    assert result.players[0].ownership_pct == 12.5


def test_compute_player_pool_ownership_pct_none_when_not_retrieved(tmp_path: Path):
    # ownership_retrieved defaults to False -- a player with no
    # ownership_pct stays None, same as before this param existed.
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Nobody", "WR", "SF", "LAR", 4000)]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    assert result.players[0].ownership_pct is None


def test_compute_player_pool_ownership_pct_zero_when_retrieved_but_unmatched(tmp_path: Path):
    # An Ownership snapshot exists for this week (ownership_retrieved=True)
    # but this particular player never showed up in it -- 0% owned, not
    # "unscored."
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Nobody", "WR", "SF", "LAR", 4000)]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir, ownership_retrieved=True)
    assert result.players[0].ownership_pct == 0.0


def test_compute_player_pool_ownership_pct_real_value_wins_even_when_retrieved(tmp_path: Path):
    # A real ownership_pct (already merged in upstream) is never
    # overwritten by the retrieved-but-unmatched 0.0 fallback.
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("A", "WR", "SF", "LAR", 6000, ownership_pct=12.5)]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir, ownership_retrieved=True)
    assert result.players[0].ownership_pct == 12.5


def test_compute_player_pool_uses_formula_suggestion_when_no_override(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    save_game_environment(ge_dir, make_game_env(home_implied_total=27.0, away_implied_total=18.0))
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    # BUF's implied total (27.0) is >=24 -> top tier -> 1.0.
    assert row.game_environment_suggested == 1.0
    assert row.game_environment_override is None
    assert row.game_environment == 1.0
    # game_matchup + ownership + volume + talent all default to 2.0 -- 1 + 2 + 2 + 2 + 2 = 9.
    assert row.total == 9.0


def test_compute_player_pool_explicit_override_wins_over_suggestion(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    save_game_environment(ge_dir, make_game_env(home_implied_total=27.0, away_implied_total=18.0))
    save_entry(nfl_dir, PlayerPoolEntry(season=2025, week=9, player="Josh Allen", game_environment=0.5))
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    assert row.game_environment_suggested == 1.0
    assert row.game_environment_override == 0.5
    assert row.game_environment == 0.5
    # game_matchup + ownership + volume + talent all default to 2.0 -- 0.5 + 2 + 2 + 2 + 2 = 8.5.
    assert row.total == 8.5


def test_compute_player_pool_uses_away_teams_own_implied_total(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    save_game_environment(ge_dir, make_game_env(home_implied_total=27.0, away_implied_total=18.0))
    players = [make_player("Away Player", "WR", "NO", "BUF", 5000)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    # NO's implied total (18.0) is <20 -> bottom tier -> 0.0.
    assert row.game_environment_suggested == 0.0
    assert row.game_environment == 0.0


def test_compute_player_pool_defaults_game_environment_to_neutral_without_data(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    assert row.game_environment_suggested == 0.5
    assert row.game_environment == 0.5
    # game_matchup + ownership + volume + talent default to 2.0 each (8.0)
    # plus game_environment's own 0.5 neutral default -- 8.5.
    assert row.total == 8.5


def test_compute_player_pool_dst_has_no_ownership_or_game_environment(tmp_path: Path):
    # DSTs only ever use Game Matchup + Salary Value -- Ownership and
    # Game Environment shouldn't apply (or default) to them at all, even
    # though those fields default to something for every offensive
    # position. Regression test for a bug where DST rows picked up a
    # phantom Ownership=2.0/Game Environment=2.0 that never showed up in
    # the DST grid but silently inflated the total anyway.
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Chargers", "DST", "LAC", "ARI", 3500)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
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


def test_compute_player_pool_dst_ignores_saved_player_default(tmp_path: Path):
    # Even if a Volume/Talent Default somehow got saved for a DST (e.g.
    # leftover data from a position change), it still shouldn't apply --
    # the position gate is unconditional, not just "was this ever set".
    ge_dir, nfl_dir = dirs(tmp_path)
    save_default(nfl_dir, PlayerDefaultEntry(season=2025, player="Chargers", volume=3.0, talent=3.0))
    players = [make_player("Chargers", "DST", "LAC", "ARI", 3500)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    row = result.players[0]
    assert row.volume is None
    assert row.talent is None


def test_compute_player_pool_expected_fpts_defaults_to_salary_over_1000(tmp_path: Path):
    # No multiplier passed -- the harmless 1.0 default applies, so
    # expected_fpts is just salary / 1000, not the real DraftKings 4x.
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    assert result.players[0].expected_fpts == 7.7


def test_compute_player_pool_expected_fpts_uses_passed_in_multiplier(tmp_path: Path):
    # Matches the user's own examples: 4x multiplier, 5000 salary -> 20,
    # 9000 salary -> 36.
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [
        make_player("A", "RB", "HOU", "ARI", 5000),
        make_player("B", "RB", "HOU", "ARI", 9000),
    ]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir, multiplier=4.0)
    by_player = {p.player: p.expected_fpts for p in result.players}
    assert by_player["A"] == 20.0
    assert by_player["B"] == 36.0


def test_compute_player_pool_expected_fpts_not_included_in_total(tmp_path: Path):
    # expected_fpts is purely informational -- it must never bleed into
    # the judgment-call Total sum.
    ge_dir, nfl_dir = dirs(tmp_path)
    players = [make_player("Nobody", "WR", "SF", "LAR", 4000)]
    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir, multiplier=4.0)
    row = result.players[0]
    assert row.expected_fpts == 16.0
    assert row.total == 8.5


def test_compute_player_pool_returns_saved_game_environment_entries(tmp_path: Path):
    ge_dir, nfl_dir = dirs(tmp_path)
    save_game_environment(ge_dir, make_game_env())
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    result = compute_player_pool(players, 2025, 9, PLATFORM, ge_dir, nfl_dir)
    assert len(result.game_environment) == 1
    assert result.game_environment[0].game_key == "BUF-NO"
