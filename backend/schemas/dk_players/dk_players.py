"""
DK Players -- a season-long, cumulative player log (Name, Position, Roster
Position, TeamAbbrev, Week, Salary, %Drafted, FPTS, Non_TD_FPTS, TD_FPTS),
one row per player per week, modeled directly on the person's own
hand-maintained DK-Players.csv from previous seasons. Two explicit actions
build this up over a season (see backend/services/dk_players/
dk_players_engine.py):

1. add_week_players() -- Monday/Tuesday, once a new week's Salary File is
   uploaded (backend/repositories/dk_salary/salary_snapshot_repo.py):
   appends that week's players with Salary filled in and %Drafted/FPTS/
   Non_TD_FPTS/TD_FPTS all zeroed. Roster Position (e.g. "RB/FLEX") isn't
   in OwnershipPlayer -- see derive_roster_position() for why it's safe to
   re-derive from `position` alone instead of threading a new field
   through the shared salary loader.

2. calculate_week_points() -- once that week's 4 FantasyData stat files
   (QB/RB/WR/TE, see backend/repositories/dk_players/weekly_stats_repo.py)
   and Contest Standings (backend/repositories/contest_results/
   contest_standings_repo.py) are both uploaded: backfills that week's
   existing rows. FPTS and %Drafted come straight from Contest Standings
   (ground truth, never recomputed -- same number Contest Results' own
   ContestResultRow.fpts/pct_drafted show). TD_FPTS is (Passing TD * 4) +
   (Rushing TD * 6) + (Receiving TD * 6) from the stat files, and
   Non_TD_FPTS is simply FPTS - TD_FPTS -- NOT an independent DK-scoring
   recomputation from yardage/receptions/etc. This mirrors the person's
   own prior Colab scripts exactly (they subtract TD points from the
   contest's own reported FPTS rather than re-deriving the whole scoring
   formula).

Unlike every other per-(season, week, platform) snapshot in this app
(Salary File, Contest Standings, ...), this file is per-(season, platform)
and keeps growing across weeks rather than being overwritten each time --
see backend/repositories/dk_players/dk_players_repo.py's own docstring.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DkPlayerRow(BaseModel):
    name: str
    position: str
    roster_position: str
    team: str
    week: int
    salary: int
    pct_drafted: float
    fpts: float
    non_td_fpts: float
    td_fpts: float


class DkPlayersResult(BaseModel):
    season: int
    platform: str
    players: list[DkPlayerRow]


class DkPlayersWeekStatus(BaseModel):
    """Whether `week` already has rows in the tracker, and whether those
    rows already have calculated points -- lets the frontend decide what
    the "Add Week N Players" confirm message should say (or whether to
    show one at all) before actually calling add-week."""

    week: int
    exists: bool
    player_count: int
    has_calculated_points: bool


class AddWeekPlayersResult(BaseModel):
    week: int
    added_count: int
    replaced: bool


class PossibleStatNameMismatch(BaseModel):
    """One tracker row that didn't match the stat file by name, but DOES
    have a close-spelling candidate in that file this week -- worth adding
    a Name Alias for (see Settings). `tracker_name` is the tracker's own
    spelling (e.g. "James Cook III"); `suggested_match` is the close
    candidate found in the stat file (e.g. "James Cook")."""

    tracker_name: str
    suggested_match: str


class CalculateWeekPointsResult(BaseModel):
    week: int
    updated_count: int
    # Which of QB/RB/WR/TE simply have no stat file uploaded yet for this
    # week -- checked BEFORE name-matching, so a whole missing file shows
    # up here once instead of every one of that position's players
    # individually cluttering the two lists below.
    missing_stat_files: list[str]
    # Players in this week's tracker rows whose position's stat file WAS
    # uploaded but who still had no matching row in it by exact name --
    # split into two groups by backend/services/dk_players/
    # dk_players_engine.py's suggest_stat_file_match, since a flat list
    # buries a real alias problem among players who simply didn't play:
    #
    # - possible_stat_name_mismatches: a close-spelling candidate WAS found
    #   in the stat file (e.g. "James Cook III" vs. the file's own "James
    #   Cook") -- worth adding a Name Alias for in Settings.
    # - no_stats_recorded: no candidate at all was found anywhere in the
    #   stat file this week -- most likely this player simply didn't
    #   record a stat line (inactive/injured/bye), not a spelling problem.
    #
    # Either way TD_FPTS/Non_TD_FPTS are left at whatever they were (0 on
    # a first run) rather than guessed. DST is never included in either
    # list -- there's no stat file for defenses in the first place.
    possible_stat_name_mismatches: list[PossibleStatNameMismatch]
    no_stats_recorded: list[str]
    # Same "no exact match" idea for Contest Standings -- no match means
    # %Drafted/FPTS (and therefore Non_TD_FPTS) are left unchanged for
    # that player. Not split the same way as the stat-file lists above --
    # Contest Standings is the one ground-truth source, so there's no
    # equivalent "simply wasn't scraped" explanation to distinguish from a
    # spelling issue.
    unmatched_contest_players: list[str]


class WeeklyStatsImportResult(BaseModel):
    season: int
    week: int
    position: Literal["QB", "RB", "WR", "TE"]
    row_count: int
