"""
Building a matchup's own key/display label from whichever side is home and
which is away -- shared by every tab that lets someone filter by "game"
(Salary Blocks' position-blocks.py/game_blocks.py, Game Logs and Game Logs
Against's build_game_options in game_logs_engine.py).

Before this module existed, each of those built its own label by just
alphabetically joining the two team codes with " vs " (e.g. "ARI vs LAR"),
discarding the home/away information their own source data actually had
available (OwnershipPlayer.is_home for Salary Blocks, a ScheduleRow's own
GameLocation for Game Logs) -- a real, user-visible bug (the "vs" label
never actually indicated which team was playing at home), not a design
choice. game_label() below is the one place that decision gets made now,
so every tab's Game filter renders the same "AWAY @ HOME" convention
Ownership Summary's own per-player Opp column already used (see frontend/
src/components/playerDisplay.tsx's opponentLabel) -- and any future
generates-a-game-filter tab gets the fix for free by reusing this.

game_key() is unchanged from every call site's prior inline version --
still an alphabetically-sorted, order-independent identifier, since the
*key* only needs to round-trip through a URL param and match regardless of
which side of the matchup a given player/row happens to be on. Only the
*label* needed fixing.
"""

from __future__ import annotations


def game_key(team_a: str, team_b: str) -> str:
    """Stable, order-independent identifier for a matchup -- "ARI-LAR"
    regardless of whether team_a/team_b is the home or away side. Matches
    the "-".join(sorted(...)) form every Game filter chip already sends
    back as its own query param."""
    return "-".join(sorted((team_a, team_b)))


def game_label(away_team: str, home_team: str) -> str:
    """"NO @ DET" -- away team first, same "AWAY@HOME" convention DK's own
    salary export uses (see backend/services/dk_salary/dk_salary_parsing.py's
    parse_game_info), just with spaces for readability. Callers that don't
    know which side is home/away (a malformed or missing home/away signal)
    should fall back to their own "TEAM_A vs TEAM_B" label instead of
    calling this with a guess -- this function always renders its input as
    if it's known-correct home/away, it doesn't hedge internally."""
    return f"{away_team} @ {home_team}"


def resolve_away_home(team: str, opponent: str, team_is_home: bool | None) -> tuple[str, str] | None:
    """(away, home) for a `team`/`opponent` pair given whether `team` is the
    home side -- or None if that isn't known (team_is_home is None), so
    callers can fall back to an alphabetical "vs" label instead of
    fabricating a home/away split from nothing. This is the shared
    resolution step for sources that track home/away as a per-side boolean
    (OwnershipPlayer.is_home) rather than a labeled schedule row -- Game
    Logs' ScheduleRow already names its own Home/Away side directly and has
    no need for this helper."""
    if team_is_home is None:
        return None
    return (team, opponent) if not team_is_home else (opponent, team)
