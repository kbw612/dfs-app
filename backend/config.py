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

    request_timeout_seconds: int = 30

    # The React frontend runs as its own dev server (Vite's default port)
    # rather than being served by this app, so CORS has to be opened up
    # explicitly for it -- see main.py.
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
