"""
Game Preview Phase D -- per-team injury summary groups, built from the
same latest depth-chart snapshot Usage Bumps already reads plus Star
Players, grouped exactly the way this feature was scoped when it was
requested: Offensive Line (depth 1-2), Defensive Front (defensive line +
linebackers combined, depth 1-2), Defensive Backs (depth 1-2), and
offensive skill positions (QB/RB/WR/TE, depth 1 through 4). One
independent group per team -- a group with no qualifying injury this week
simply produces no group at all (same "no signal, no row" spirit as every
other Phase B/C signal in this feature), so a fully-healthy team's own
group list comes back empty rather than four groups all saying "none."

Star Players do NOT get their own group -- an earlier version of this
feature had a fifth "Star Players (any position/depth)" group, but per
explicit feedback that's been folded into a per-entry `starred` flag
instead (see GamePreviewInjuryEntry.starred): a starred player who's hurt
still only shows up in whichever position group they'd already qualify
for, just with that flag set so the frontend can put a gold star next to
their name -- the same "icon next to the name, not a whole extra row"
convention Depth Charts/Injury Report already use. A starred player deep
enough on the depth chart to miss every group's own cutoff (e.g. a
starred WR5, past the skill group's depth-4 cutoff) simply doesn't appear
anywhere, same as any other non-qualifying player.

Position codes are footballguys.com's own depth-chart labels (see
backend/services/depth_charts/scraper.py's DESIRED_POSITION_ORDER) --
Defensive Line and Linebacker are two disjoint label sets there (e.g.
"LDE"/"RDT" vs. "WLB"/"MLB"), combined here into one "Defensive Front"
group per this feature's own scoping decision, rather than shown as two
separate groups.
"""

from __future__ import annotations

from backend.schemas.depth_charts.snapshot import Snapshot
from backend.schemas.game_preview.game_preview import GamePreviewInjuryEntry, GamePreviewInjuryGroup
from backend.schemas.star_players.star_players import StarPlayersResult

OFFENSIVE_LINE_POSITIONS = {"LT", "LG", "C", "RG", "RT"}
DEFENSIVE_LINE_POSITIONS = {"LDE", "RDE", "NT", "LDT", "RDT"}
LINEBACKER_POSITIONS = {"WLB", "SLB", "MLB", "LILB", "RILB"}
DEFENSIVE_FRONT_POSITIONS = DEFENSIVE_LINE_POSITIONS | LINEBACKER_POSITIONS
DEFENSIVE_BACK_POSITIONS = {"LCB", "RCB", "SCB", "FS", "SS"}
OFFENSIVE_SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

# Offensive skill positions are summarized through depth 4 (a team's
# fourth-string WR is still fantasy-relevant if hurt); O-Line, Defensive
# Front, and Defensive Backs all go through depth 2 (an immediate backup
# at those groups is worth flagging too, per explicit feedback extending
# them beyond starters-only).
MAX_SKILL_DEPTH = 4
MAX_NON_SKILL_DEPTH = 2


def build_team_injury_groups(team: str, snapshot: Snapshot, star_players: StarPlayersResult) -> list[GamePreviewInjuryGroup]:
    """Returns [] entirely when `team` has no row in `snapshot` at all
    (team not in this scrape, or its own team_abbrev didn't resolve --
    see Team.team_abbrev's own docstring). Otherwise returns one
    GamePreviewInjuryGroup per group that has >=1 qualifying entry, in a
    fixed order: O-Line, Defensive Front, Defensive Backs, Skill
    Positions."""
    team_row = next((t for t in snapshot.teams if t.team_abbrev == team), None)
    if team_row is None:
        return []

    starred_names = {p.player for p in star_players.players if p.team == team}

    ol_entries: list[GamePreviewInjuryEntry] = []
    front_entries: list[GamePreviewInjuryEntry] = []
    db_entries: list[GamePreviewInjuryEntry] = []
    skill_entries: list[GamePreviewInjuryEntry] = []

    for position, players in team_row.positions.items():
        for depth, p in enumerate(players, start=1):
            if p.status is None:
                continue
            entry = GamePreviewInjuryEntry(
                player=p.player,
                position=position,
                depth=depth,
                status=p.status,
                starred=p.player in starred_names,
            )
            if position in OFFENSIVE_LINE_POSITIONS and depth <= MAX_NON_SKILL_DEPTH:
                ol_entries.append(entry)
            elif position in DEFENSIVE_FRONT_POSITIONS and depth <= MAX_NON_SKILL_DEPTH:
                front_entries.append(entry)
            elif position in DEFENSIVE_BACK_POSITIONS and depth <= MAX_NON_SKILL_DEPTH:
                db_entries.append(entry)
            elif position in OFFENSIVE_SKILL_POSITIONS and depth <= MAX_SKILL_DEPTH:
                skill_entries.append(entry)

    groups: list[GamePreviewInjuryGroup] = []
    if ol_entries:
        groups.append(GamePreviewInjuryGroup(label="O-Line (depth 1-2)", entries=ol_entries))
    if front_entries:
        groups.append(GamePreviewInjuryGroup(label="Defensive Front (depth 1-2)", entries=front_entries))
    if db_entries:
        groups.append(GamePreviewInjuryGroup(label="Defensive Backs (depth 1-2)", entries=db_entries))
    if skill_entries:
        groups.append(GamePreviewInjuryGroup(label="Skill Positions (depth 1-4)", entries=skill_entries))
    return groups
