"""
Reads and writes Blink's groups CSV:

    Group,GroupName,Id,Name,AnchorPlayer,MinGroup,MaxGroup,Pct
    0,Det,44664465,Jahmyr Gibbs,false,2,4,1

One row per player. Group is the group's position (0, 1, ...). Each group's
Min/Max/Pct repeat on every row. Pct is a fraction in the file ("1", "0.80");
the app keeps it as a percent. Written with "\n" line endings and a trailing
newline, as Blink's own export is.
"""

from __future__ import annotations

import csv
import io

from backend.schemas.player_groups.player_groups import GroupPlayer, PlayerGroup

HEADER = ["Group", "GroupName", "Id", "Name", "AnchorPlayer", "MinGroup", "MaxGroup", "Pct"]


def _pct_text(pct: float) -> str:
    fraction = pct / 100.0
    return "1" if fraction == 1 else f"{fraction:.2f}"


def write_groups_csv(groups: list[PlayerGroup]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    for index, g in enumerate(groups):
        for p in g.players:
            writer.writerow([index, g.name, p.id, p.name, "true" if p.anchor else "false", g.min, g.max, _pct_text(g.pct)])
    return out.getvalue()


def parse_groups_csv(text: str) -> list[PlayerGroup]:
    """Groups in file order (by Group number). Raises ValueError on a file that
    isn't a Blink groups export."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows or [h.strip() for h in rows[0]] != HEADER:
        raise ValueError(f"Expected a groups file with the header {','.join(HEADER)}")
    by_index: dict[int, PlayerGroup] = {}
    for row in rows[1:]:
        if len(row) != len(HEADER):
            continue
        index, name, pid, pname, anchor, mn, mx, pct = (c.strip() for c in row)
        g = by_index.get(int(index))
        if g is None:
            g = PlayerGroup(name=name, pct=round(float(pct) * 100.0, 2), min=int(mn), max=int(mx), players=[])
            by_index[int(index)] = g
        g.players.append(GroupPlayer(id=pid, name=pname, anchor=anchor.lower() == "true"))
    return [by_index[i] for i in sorted(by_index)]


def merge_groups(existing: list[PlayerGroup], imported: list[PlayerGroup], replace_all: bool) -> list[PlayerGroup]:
    """Same-named groups (case-insensitive) are replaced in place by the
    imported one; other existing groups stay; new ones are appended."""
    if replace_all:
        return list(imported)
    merged = list(existing)
    for g in imported:
        i = next((k for k, e in enumerate(merged) if e.name.lower() == g.name.lower()), None)
        if i is None:
            merged.append(g)
        else:
            merged[i] = g
    return merged
