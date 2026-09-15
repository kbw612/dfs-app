from pathlib import Path

from backend.repositories.ownership.projections_repo import save_projections_csv
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.player_pool.enrichment import enrich_players_for_week

PLATFORM = "DraftKings"

_CSV_HEADER = "Player,Position,Team,Opponent,Salary,% ownership\n"


def make_player(player: str, position: str, team: str, opponent: str, salary: int) -> OwnershipPlayer:
    return OwnershipPlayer(
        player=player,
        position=position,
        team=team,
        opponent=opponent,
        is_home=True,
        salary=salary,
        ownership_pct=None,
    )


def test_enrich_players_for_week_ownership_retrieved_false_when_no_projections_uploaded(tmp_path: Path):
    # No projections file at all for this (season, week, platform) --
    # ownership_retrieved should be False, and every player's
    # ownership_pct should stay None rather than resolving to 0.0 (that
    # fallback is only for a real, uploaded-but-unmatched projections
    # file -- see engine.py's compute_player_pool docstring).
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    enriched, ownership_retrieved = enrich_players_for_week(players, 2025, 9, PLATFORM, tmp_path)

    assert ownership_retrieved is False
    assert enriched[0].ownership_pct is None


def test_enrich_players_for_week_merges_real_ownership_projections(tmp_path: Path):
    # This is the real bug this test guards against: enrichment used to
    # read the old, effectively-dead OwnershipSnapshot pipeline (see this
    # module's docstring) instead of the Settings-uploaded projections
    # file the Ownership tab itself reads -- so a real, current upload
    # like this one was silently ignored and every player fell back to
    # 0%. This proves the currently-uploaded projections CSV is what
    # actually gets merged in now.
    csv_text = _CSV_HEADER + "Josh Allen,QB,BUF,vs NO,7700,18.5\n"
    save_projections_csv(tmp_path, 2025, 9, PLATFORM, csv_text)
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    enriched, ownership_retrieved = enrich_players_for_week(players, 2025, 9, PLATFORM, tmp_path)

    assert ownership_retrieved is True
    assert enriched[0].ownership_pct == 18.5


def test_enrich_players_for_week_scoped_to_week(tmp_path: Path):
    # A projections upload for a different week shouldn't be picked up --
    # each week's file is independent, same as the salary file itself.
    csv_text = _CSV_HEADER + "Josh Allen,QB,BUF,vs NO,7700,18.5\n"
    save_projections_csv(tmp_path, 2025, 8, PLATFORM, csv_text)
    players = [make_player("Josh Allen", "QB", "BUF", "NO", 7700)]

    enriched, ownership_retrieved = enrich_players_for_week(players, 2025, 9, PLATFORM, tmp_path)

    assert ownership_retrieved is False
    assert enriched[0].ownership_pct is None
