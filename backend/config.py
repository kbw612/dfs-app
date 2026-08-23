"""
Central settings for the app, loaded from environment variables (or a local
.env file). Nothing here should be hardcoded elsewhere -- this is the one
place file paths and the scrape source URL are defined, so swapping local
storage for a cloud backend later (Section 2, Phase 2 of the design doc)
means changing this file, not chasing hardcoded paths through the codebase.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DFS_APP_", env_file=".env", extra="ignore")

    source_url: str = "https://www.footballguys.com/depthcharts?type=all&1=2"

    snapshots_dir: Path = Path("./data/snapshots")
    team_info_csv: Path = Path("./config/team-info.csv")

    # Usage-bump engine (backend/services/usage_bump/engine.py) -- see
    # that module's docstring for how these three files fit together.
    usage_bump_players_json: Path = Path("./config/usage-bump-players.json")
    usage_bump_position_settings_json: Path = Path("./config/usage-bump-position-settings.json")
    player_out_settings_json: Path = Path("./config/player-out-settings.json")

    request_timeout_seconds: int = 30

    # The React frontend runs as its own dev server (Vite's default port)
    # rather than being served by this app, so CORS has to be opened up
    # explicitly for it -- see main.py.
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
