"""
Builds up the DK Players season-long tracker (backend/schemas/dk_players/
dk_players.py) one week at a time -- see that module's own docstring for
the two actions this implements (add_week_players, calculate_week_points)
and why calculating a week's points is one combined operation rather than
the two separate "Non_TD_FPTS/TD_FPTS" and "%Drafted" steps it might
sound like at first.
"""

from __future__ import annotations

import difflib
from typing import Iterable

from backend.schemas.dk_players.dk_players import (
    AddWeekPlayersResult,
    CalculateWeekPointsResult,
    DkPlayerRow,
    DkPlayersWeekStatus,
    PossibleStatNameMismatch,
)
from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.services.contest_results.contest_standings_parser import ContestReferenceRow
# Re-exported for backward compatibility -- apply_name_alias/
# name_lookup_candidates used to be defined here, now live in
# backend/services/shared/name_match.py (alongside normalize_player_name,
# the same "cross-source name matching" family of helper) since Player
# Pool's Player Defaults resolution needs them too, not just DK Players.
from backend.services.shared.name_match import apply_name_alias, name_lookup_candidates  # noqa: F401

# Name suffixes stripped before comparing "last names" in
# suggest_stat_file_match -- e.g. "James Cook III" and "James Cook" should
# be treated as sharing the last name "Cook", not "III" vs. "Cook".
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Below this difflib similarity ratio between two players' FIRST names,
# sharing a last name is not enough to suggest a match -- see
# suggest_stat_file_match's docstring for why a shared surname alone
# (Smith, Wilson, Hill, Higgins, Samuel...) is common enough in the NFL to
# be worthless as a signal on its own.
_FIRST_NAME_FUZZY_CUTOFF = 0.7

# Below this difflib similarity ratio on the FULL name, two players who
# don't even share a last name are treated as unrelated -- see
# suggest_stat_file_match.
_FULL_NAME_FUZZY_CUTOFF = 0.9

# DK's Roster Position eligibility is deterministic from a player's own
# true `position` -- RB/WR/TE are always FLEX-eligible, QB/DST never are.
# Re-deriving it here (rather than threading a new field through the
# shared dk_salary_loader.parse_dk_salary_csv) keeps that loader's own
# OwnershipPlayer output untouched for every other caller (Player Pool,
# Salary Blocks, Contest Results, ...) that has no use for this column.
_FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}


def derive_roster_position(position: str) -> str:
    return f"{position}/FLEX" if position in _FLEX_ELIGIBLE_POSITIONS else position


def _core_last_name(name: str) -> str:
    """The last "real" name token, with trailing suffixes (Jr./Sr./II-V)
    stripped first -- so "James Cook III" and "James Cook" compare as
    sharing the last name "cook" rather than "iii" vs. "cook"."""
    parts = [p.strip(".") for p in name.split()]
    while len(parts) > 1 and parts[-1].lower() in _NAME_SUFFIXES:
        parts.pop()
    return parts[-1].lower() if parts else name.lower()


def _core_first_name(name: str) -> str:
    """The first name token, lowercased -- used only to double-check a
    shared-last-name candidate in suggest_stat_file_match (see there)."""
    parts = name.split()
    return parts[0].lower() if parts else name.lower()


def suggest_stat_file_match(name: str, candidate_names: Iterable[str]) -> str | None:
    """Best-guess close-spelling match for `name` among `candidate_names`
    (a stat file's own player names for this week) -- lets
    calculate_week_points tell "this is probably a name-spelling mismatch
    worth an alias" apart from "this player simply has no row in the stat
    file this week" (typically because they didn't play/record a stat
    line that week). Returns None when nothing looks close enough to be
    worth surfacing -- that silence is itself the signal that a player
    probably just didn't play, though it isn't a certainty.

    A shared (suffix-stripped) last name is NOT treated as sufficient
    evidence on its own -- real NFL rosters have plenty of unrelated
    players sharing a common surname (Smith, Wilson, Hill, Higgins,
    Samuel, ...), so naively returning "whoever shares this last name" or
    even "whoever with this last name is textually closest" produced
    real false positives on real data, e.g. suggesting "Taysom Hill" for
    "Tyreek Hill" or "DeVonta Smith" for "Geno Smith" -- two entirely
    different players who happen to share a surname. Instead, a
    shared-last-name candidate is only trusted if the FIRST names are
    also a close match (catches the actual target case -- a dropped/added
    suffix like "James Cook III" vs. "James Cook", where the first name
    matches exactly). Candidates that don't share a last name at all are
    only surfaced when the FULL name similarity is very high, which in
    practice only happens for a single-character typo or a punctuation/
    hyphenation difference (e.g. "Unknown Runner" vs. "Unknown Runnar",
    "KeAndre Lambert-Smith" vs. "Keandre Lambert-Smith") -- not for two
    different players who merely share a first name or suffix, which is
    what let "Marvin Mims Jr." get suggested for "Marvin Harrison Jr." in
    the old single-cutoff version of this function."""
    candidates = list(candidate_names)
    if not candidates:
        return None

    target_last = _core_last_name(name)
    target_first = _core_first_name(name)
    same_last_name = [c for c in candidates if _core_last_name(c) == target_last]

    if same_last_name:
        scored = [
            (difflib.SequenceMatcher(None, target_first, _core_first_name(c)).ratio(), c)
            for c in same_last_name
        ]
        scored = [pair for pair in scored if pair[0] >= _FIRST_NAME_FUZZY_CUTOFF]
        if not scored:
            return None
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1]

    best = difflib.get_close_matches(name, candidates, n=1, cutoff=_FULL_NAME_FUZZY_CUTOFF)
    return best[0] if best else None


def week_status(existing_rows: list[DkPlayerRow], week: int) -> DkPlayersWeekStatus:
    week_rows = [r for r in existing_rows if r.week == week]
    return DkPlayersWeekStatus(
        week=week,
        exists=len(week_rows) > 0,
        player_count=len(week_rows),
        has_calculated_points=any(r.fpts != 0.0 or r.pct_drafted != 0.0 for r in week_rows),
    )


def add_week_players_rows(
    existing_rows: list[DkPlayerRow], salary_players: list[OwnershipPlayer], week: int
) -> tuple[list[DkPlayerRow], AddWeekPlayersResult]:
    """Always "replace" semantics -- drops any rows already present for
    `week` and inserts fresh ones from `salary_players`, so this function
    itself doesn't need its own separate add-vs-replace branch. Whether to
    warn/confirm before calling this at all is the API layer's job (see
    week_status): check first, and only call this once the caller (or the
    person, via a confirm dialog) has decided to proceed."""
    already_existed = any(r.week == week for r in existing_rows)
    new_week_rows = [
        DkPlayerRow(
            name=p.player,
            position=p.position,
            roster_position=derive_roster_position(p.position),
            team=p.team,
            week=week,
            salary=p.salary,
            pct_drafted=0.0,
            fpts=0.0,
            non_td_fpts=0.0,
            td_fpts=0.0,
        )
        for p in salary_players
    ]
    kept_rows = [r for r in existing_rows if r.week != week]
    result = AddWeekPlayersResult(week=week, added_count=len(new_week_rows), replaced=already_existed)
    return kept_rows + new_week_rows, result


def _aggregate_contest_data(contest_rows: list[ContestReferenceRow]) -> dict[str, tuple[float, float]]:
    """{player: (total_pct_drafted, fpts)} -- %Drafted summed across every
    roster slot a player was used in (the same real-world quirk and same
    fix as contest_results_engine.py's _build_player_rank_lookup: a player
    used at both RB and FLEX across different entries has two partial
    reference rows, and their true total ownership is the sum of both).
    FPTS is one real score for the week regardless of slot, so the last
    row seen simply wins."""
    total_pct: dict[str, float] = {}
    fpts_by_player: dict[str, float] = {}
    for row in contest_rows:
        total_pct[row.player] = total_pct.get(row.player, 0.0) + row.pct_drafted
        fpts_by_player[row.player] = row.fpts
    return {player: (total_pct[player], fpts_by_player[player]) for player in total_pct}


def calculate_week_points(
    existing_rows: list[DkPlayerRow],
    week: int,
    td_points_by_player: dict[str, float],
    contest_rows: list[ContestReferenceRow],
    name_aliases: dict[str, str],
    missing_stat_positions: list[str] | None = None,
) -> tuple[list[DkPlayerRow], CalculateWeekPointsResult]:
    """Backfills %Drafted/FPTS/Non_TD_FPTS/TD_FPTS on `week`'s existing
    rows only -- every other week's rows pass through untouched.

    FPTS and %Drafted come straight from `contest_rows` (Contest
    Standings' own reference table -- ground truth, never recomputed).
    TD_FPTS comes from `td_points_by_player` (the 4 FantasyData stat
    files, see weekly_stats_loader.merge_td_points). Non_TD_FPTS is
    FPTS - TD_FPTS using whichever of those two is freshest -- NOT an
    independent DK-scoring recomputation from yardage/receptions/etc.,
    mirroring the person's own prior Colab script exactly.

    A row whose player matches neither source keeps its existing values
    entirely and is reported in the result's stat-side lists AND
    unmatched_contest_players; a row matching only one source still gets
    Non_TD_FPTS recomputed using that source's fresh number plus the
    OTHER field's last-known value (better than leaving a stale
    Non_TD_FPTS/TD_FPTS pairing that no longer sums correctly).

    A stat-file miss is further split via suggest_stat_file_match into
    possible_stat_name_mismatches (a close-spelling candidate exists in
    the stat file -- probably a name alias is needed) vs. no_stats_recorded
    (nothing close exists at all -- probably this player just didn't
    record a stat line that week) -- see that function's own docstring and
    CalculateWeekPointsResult's for why this split exists.

    Each source (stat file, contest standings) is matched independently
    via name_lookup_candidates -- a name alias is really "these two
    sources spell this player differently," but which of the two spellings
    a *given* source uses isn't fixed: Contest Standings might already
    agree with the tracker's own spelling (no translation needed there)
    while the stat file needs the alias's other spelling, or vice versa.
    Trying the row's raw name first and only falling back to the alias
    mapping (forward or reverse) if that misses means a source that
    already matches natively is never broken by a translation it didn't
    need -- see name_lookup_candidates' own docstring.

    `missing_stat_positions` (from the API layer, which knows definitively
    which of the 4 stat files actually exist -- see backend/api/
    dk_players/calculate_week.py) keeps a whole missing file from
    cluttering the two stat-side lists with every one of that position's
    players individually; those players simply aren't checked against
    td_points_by_player at all, and the missing position shows up once in
    the result's own missing_stat_files instead. DST is never checked
    either way -- there's no stat file for defenses in this data model."""
    contest_lookup = _aggregate_contest_data(contest_rows)
    missing_positions = set(missing_stat_positions or [])
    stat_file_names = td_points_by_player.keys()

    possible_stat_name_mismatches: list[PossibleStatNameMismatch] = []
    no_stats_recorded: list[str] = []
    unmatched_contest_players: list[str] = []
    updated_rows: list[DkPlayerRow] = []
    updated_count = 0

    for row in existing_rows:
        if row.week != week:
            updated_rows.append(row)
            continue

        candidates = name_lookup_candidates(row.name, name_aliases)
        stat_checkable = row.position != "DST" and row.position not in missing_positions

        td_points = None
        if stat_checkable:
            for candidate in candidates:
                td_points = td_points_by_player.get(candidate)
                if td_points is not None:
                    break

        contest_data = None
        for candidate in candidates:
            contest_data = contest_lookup.get(candidate)
            if contest_data is not None:
                break

        if stat_checkable and td_points is None:
            suggested_match = suggest_stat_file_match(row.name, stat_file_names)
            if suggested_match is not None:
                possible_stat_name_mismatches.append(
                    PossibleStatNameMismatch(tracker_name=row.name, suggested_match=suggested_match)
                )
            else:
                no_stats_recorded.append(row.name)
        if contest_data is None:
            unmatched_contest_players.append(row.name)

        if td_points is None and contest_data is None:
            updated_rows.append(row)
            continue

        new_pct_drafted = contest_data[0] if contest_data is not None else row.pct_drafted
        new_fpts = contest_data[1] if contest_data is not None else row.fpts
        new_td_fpts = td_points if td_points is not None else row.td_fpts
        new_non_td_fpts = round(new_fpts - new_td_fpts, 2)

        updated_rows.append(
            DkPlayerRow(
                name=row.name,
                position=row.position,
                roster_position=row.roster_position,
                team=row.team,
                week=row.week,
                salary=row.salary,
                pct_drafted=new_pct_drafted,
                fpts=new_fpts,
                non_td_fpts=new_non_td_fpts,
                td_fpts=new_td_fpts,
            )
        )
        updated_count += 1

    result = CalculateWeekPointsResult(
        week=week,
        updated_count=updated_count,
        missing_stat_files=sorted(missing_positions),
        possible_stat_name_mismatches=possible_stat_name_mismatches,
        no_stats_recorded=no_stats_recorded,
        unmatched_contest_players=unmatched_contest_players,
    )
    return updated_rows, result
