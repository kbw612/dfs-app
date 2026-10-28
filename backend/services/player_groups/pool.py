"""The player pool behind the Player Groups tab: every player in the week's
contest salary file (DK ID, position, team, game, salary), plus summaries of
groups against it."""

from __future__ import annotations

import csv
import io

from backend.schemas.player_groups.player_groups import GameChip, GroupSummary, PlayerGroup, PoolPlayer, SummaryPlayer
from backend.services.dk_salary.dk_salary_parsing import parse_game_info
from backend.services.ownership.parsing import normalize_team_abbrev, parse_salary
from backend.services.shared.game_matchup import game_label, resolve_away_home


def parse_pool(salary_csv_text: str) -> tuple[list[PoolPlayer], list[GameChip]]:
    players: list[PoolPlayer] = []
    games: dict[str, GameChip] = {}
    for row in csv.DictReader(io.StringIO(salary_csv_text)):
        try:
            team = normalize_team_abbrev(row["TeamAbbrev"])
            opponent, is_home = parse_game_info(row["Game Info"], team)
            pid = (row.get("ID") or "").strip()
            name = (row.get("Name") or "").strip()
            salary = parse_salary(row["Salary"])
            position = row["Position"].strip()
        except (KeyError, ValueError):
            continue
        if not pid or not name:
            continue
        key = "-".join(sorted([team, opponent]))
        players.append(PoolPlayer(id=pid, name=name, position=position, team=team, opponent=opponent, salary=salary, game_key=key))
        if key not in games:
            away_home = resolve_away_home(team, opponent, is_home)
            label = game_label(*away_home) if away_home else f"{min(team, opponent)} vs {max(team, opponent)}"
            games[key] = GameChip(key=key, label=label, teams=sorted([team, opponent]))
    return players, sorted(games.values(), key=lambda g: g.label)


def min_salaries(players: list[PoolPlayer]) -> dict[str, int]:
    """The lowest salary at each position across the whole contest pool."""
    out: dict[str, int] = {}
    for p in players:
        out[p.position] = min(p.salary, out.get(p.position, p.salary))
    return out


def filter_pool(
    players: list[PoolPlayer],
    game_keys: list[str],
    position: str,
    team: str,
    q: str,
    pool_names: set[str] | None = None,
    hide_min_salary: bool = False,
) -> list[PoolPlayer]:
    """Filters (all optional) then sorts salary high to low (name breaks
    ties). `pool_names`, when given, keeps only those players (My Player
    Pool); it combines with the other filters, e.g. RBs in my pool.
    `hide_min_salary` drops players priced at their position's contest-wide
    minimum (the filler players), whichever games are selected."""
    floor = min_salaries(players) if hide_min_salary else {}
    q = q.strip().lower()
    out = [
        p
        for p in players
        if (not game_keys or p.game_key in game_keys)
        and position in ("", "ALL", p.position)
        and (not team or p.team == team)
        and (not q or q in p.name.lower())
        and (pool_names is None or p.name in pool_names)
        and (not hide_min_salary or p.salary > floor[p.position])
    ]
    return sorted(out, key=lambda p: (-p.salary, p.name))


def summarize(groups: list[PlayerGroup], players: list[PoolPlayer]) -> list[GroupSummary]:
    by_id = {p.id: p for p in players}
    out = []
    for g in groups:
        known = [by_id[x.id] for x in g.players if x.id in by_id]
        out.append(
            GroupSummary(
                **g.model_dump(exclude={"players"}),
                players=[
                    SummaryPlayer(
                        **x.model_dump(),
                        salary=by_id[x.id].salary if x.id in by_id else None,
                        position=by_id[x.id].position if x.id in by_id else None,
                    )
                    for x in g.players
                ],
                player_count=len(g.players),
                salary_total=sum(p.salary for p in known),
                missing_ids=[x.id for x in g.players if x.id not in by_id],
            )
        )
    return out


def validate_groups(groups: list[PlayerGroup]) -> list[str]:
    """Problems that block saving (returned as messages); empty list = fine."""
    problems: list[str] = []
    seen: set[str] = set()
    for g in groups:
        name = g.name.strip().lower()
        if name in seen:
            problems.append(f"Two groups are named '{g.name}'.")
        seen.add(name)
        if g.min > g.max:
            problems.append(f"'{g.name}': Min ({g.min}) is more than Max ({g.max}).")
        ids = [p.id for p in g.players]
        if len(ids) != len(set(ids)):
            problems.append(f"'{g.name}' has the same player twice.")
    return problems
