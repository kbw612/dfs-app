"""
Central settings for the app, loaded from environment variables (or a local
.env file). Nothing here should be hardcoded elsewhere -- this is the one
place file paths and the scrape source URL are defined, so swapping local
storage for a cloud backend later (Section 2, Phase 2 of the design doc)
means changing this file, not chasing hardcoded paths through the codebase.
"""

from typing import Optional

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DFS_APP_", env_file=".env", extra="ignore")

    # Where backend/services/depth_charts/scraper.py scrapes NFL depth
    # charts from.
    nfl_depth_chart_url: str = "https://www.footballguys.com/depthcharts?type=all&1=2"

    snapshots_dir: Path = Path("./data/snapshots")
    team_info_csv: Path = Path("./config/team-info.csv")

    # Usage-bump engine (backend/services/usage_bump/engine.py) -- see
    # that module's docstring for how these three files fit together.
    usage_bump_players_json: Path = Path("./config/usage-bump-players.json")
    usage_bump_position_settings_json: Path = Path("./config/usage-bump-position-settings.json")
    player_out_settings_json: Path = Path("./config/player-out-settings.json")

    # Ownership/leverage engine (backend/services/ownership/engine.py).
    # ownership_source_username/password authenticate against
    # oneweekseason.com -- deliberately no default (None until set via env
    # or .env), so a missing credential fails loudly at scrape time rather
    # than silently trying an empty login. Never hardcode real values here.
    ownership_source_url: str = "https://oneweekseason.com"
    ownership_source_username: Optional[str] = None
    ownership_source_password: Optional[str] = None
    ownership_snapshots_dir: Path = Path("./data/ownership_snapshots")
    ownership_leverage_tiers_json: Path = Path("./config/ownership-leverage-tiers.json")

    # Temporary stand-in for live scraping (backend/services/ownership/
    # csv_loader.py) -- reads DK ownership CSVs dropped in this directory
    # instead of logging into oneweekseason.com. Filenames follow the same
    # "ownership-projections-week{N}.csv" / "dst-ownership-projections-
    # week{N}.csv" convention as the original notebook this app was ported
    # from, so any future week's export just needs to land here with a
    # matching name -- no code changes.
    ownership_mock_dir: Path = Path("./data/ownership_mock")

    # Player Pool (backend/services/player_pool/engine.py) -- manually
    # entered weekly scores, see repositories/player_pool/entries_repo.py
    # for the on-disk shape.
    player_pool_dir: Path = Path("./data/player_pool")

    # New per-season NFL data layout -- data/nfl/{season}/... -- starting
    # with the shared DK salary CSV (uploaded via POST /api/dk-salary/
    # import-csv, see repositories/dk_salary/salary_snapshot_repo.py).
    # Salary Blocks and Player Pool both read this; deliberately separate
    # from ownership_snapshots_dir -- neither tab depends on the
    # Ownership tab having loaded anything for the week (which keeps
    # using its own file's salary for itself). Ownership and the other
    # snapshot-backed resources still live under the flat data/ layout
    # below for now -- they'll move under here too in a later pass.
    nfl_data_dir: Path = Path("./data/nfl")

    # Game Environment (backend/services/game_environment/scoring.py) --
    # weekly Vegas-line data (spread, implied totals, over/under) shared
    # across tabs, not owned by Player Pool specifically. See
    # repositories/game_environment/game_environment_repo.py.
    game_environment_dir: Path = Path("./data/game_environment")

    # Player Attributes (backend/repositories/player_attributes/
    # entries_repo.py) -- Volume/Talent, carried forward from the most
    # recent earlier week same as they used to be inside Player Pool's own
    # storage; split out into a shared resource, not owned by Player Pool
    # specifically.
    player_attributes_dir: Path = Path("./data/player_attributes")

    # Current Week (backend/repositories/current_week/current_week_repo.py)
    # -- the single (season, week) pointer shared by every weekly tab, set
    # via one shared control (frontend/src/App.tsx) instead of each tab
    # keeping its own copy.
    current_week_dir: Path = Path("./data/current_week")

    # Platform Settings (backend/repositories/platform_settings/
    # platform_settings_repo.py) -- the single (platform, contest) pair
    # shared by every tab that touches a platform-specific file, set via
    # one shared control (Settings tab's top panel) instead of each tab
    # guessing. See backend/services/platform_settings/prefix.py for how
    # `platform` maps to the shared salary/ownership filename prefix.
    platform_settings_dir: Path = Path("./data/platform_settings")

    request_timeout_seconds: int = 30

    # The React frontend runs as its own dev server (Vite's default port)
    # rather than being served by this app, so CORS has to be opened up
    # explicitly for it -- see main.py.
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
