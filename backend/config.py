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

    # New per-season NFL data layout -- data/nfl/{season}/... -- starting
    # with the shared DK salary CSV (uploaded via POST /api/dk-salary/
    # import-csv, see repositories/dk_salary/salary_snapshot_repo.py).
    # Salary Blocks and Player Pool both read this; deliberately separate
    # from ownership_snapshots_dir -- neither tab depends on the
    # Ownership tab having loaded anything for the week (which keeps
    # using its own file's salary for itself). Also home to Player
    # Selection's per-week override files, Player Pool's own per-week
    # score entries (repositories/player_pool/entries_repo.py), Player
    # Defaults' per-season data/nfl/{season}/settings/player_factors.json
    # (see repositories/player_defaults/defaults_repo.py), and Platform
    # Settings' per-season data/nfl/{season}/settings/platform_settings.json
    # (see repositories/platform_settings/platform_settings_repo.py).
    # Ownership and the other snapshot-backed resources still live under
    # the flat data/ layout below for now -- they'll move under here too
    # in a later pass.
    nfl_data_dir: Path = Path("./data/nfl")

    # Game Environment (backend/services/game_environment/scoring.py) --
    # weekly Vegas-line data (spread, implied totals, over/under) shared
    # across tabs, not owned by Player Pool specifically. See
    # repositories/game_environment/game_environment_repo.py.
    game_environment_dir: Path = Path("./data/game_environment")

    # Vegas-line source for the Vegas Lines tab's scrape button (backend/
    # services/vegas_lines/scraper.py) -- one public page per
    # (season, week) listing every game's implied home/away totals and
    # over/under, e.g. https://oneweekseason.com/week/week-1-2026/. No
    # login required for this page, unlike Ownership's basic-ownership-dk
    # scrape on the same site (see ownership_source_username/password
    # above) -- verified live before building the scraper.
    oneweekseason_week_url_template: str = "https://oneweekseason.com/week/week-{week}-{season}/"

    # Current Week (backend/repositories/current_week/current_week_repo.py)
    # -- the single (season, week) pointer shared by every weekly tab, set
    # via one shared control (frontend/src/App.tsx) instead of each tab
    # keeping its own copy.
    current_week_dir: Path = Path("./data/current_week")

    # Salary Multiplier (backend/repositories/salary_multiplier/
    # salary_multiplier_repo.py) -- one saved value per platform, not
    # scoped to season/week at all (it's a property of that platform's
    # salary scale, e.g. DraftKings' rough $1000-per-fantasy-point curve --
    # see backend/services/salary_multiplier/engine.py's default of 4.0).
    # Deliberately its own top-level dir rather than living under
    # nfl_data_dir, since nothing here is per-season.
    salary_multiplier_dir: Path = Path("./data/salary_multiplier")

    # Name Aliases (backend/repositories/name_aliases/name_aliases_repo.py)
    # -- a small, global (not per-season/week) list of alias -> canonical
    # player-name pairs, e.g. "James Cook III" -> "James Cook", maintained
    # by hand in Settings. Applied wherever DK Players (backend/services/
    # dk_players/dk_players_engine.py) matches player names across the
    # Salary File, the weekly FantasyData stat files, and Contest
    # Standings -- those three sources don't always spell a name the same
    # way. Deliberately its own JSON file, same pattern as
    # usage_bump_players_json above, rather than scoped under
    # nfl_data_dir, since a name mismatch isn't specific to one season.
    name_aliases_json: Path = Path("./config/name-aliases.json")

    request_timeout_seconds: int = 30

    # The React frontend runs as its own dev server (Vite's default port)
    # rather than being served by this app, so CORS has to be opened up
    # explicitly for it -- see main.py.
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
