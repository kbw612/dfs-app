"""
Player Pool Signals: for every player on this week's slate, a list of plain-language
reasons (chips) to include or avoid him, built from the weekly FantasyData stat
files, the Vegas lines and the depth-chart injury statuses. See thresholds.py for
every cut-off; each rule returns zero or more SignalChip.

Net = positive chips minus negative chips. Usage rules look at the last `last_x`
completed weeks.
Opponent history follows `opponent_scope` ("last" = same last X weeks, "season" = every completed week). A rule only fires when its data exists, so early weeks stay quiet.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean

from backend.schemas.ownership.ownership import OwnershipPlayer
from backend.schemas.player_signals.player_signals import SignalChip, SignalPlayer
from backend.schemas.vegas_lines.vegas_lines import VegasLinesSnapshot
from backend.services.shared.name_match import normalize_player_name

POSITIONS = ("QB", "RB", "WR", "TE", "DST")
OUT_STATUSES = {"O", "IR", "PUP", "NFI", "SUS", "DNR"}
SKIP_STATUSES = OUT_STATUSES  # players listed out are left off the board


@dataclass
class Row:
    name: str
    norm: str
    team: str
    opp: str
    week: int
    pos: str
    s: dict[str, float] = field(default_factory=dict)

    def g(self, key: str, default: float = 0.0) -> float:
        return self.s.get(key, default)

    @property
    def touches(self) -> float:
        return self.g("rushing_att") + self.g("receiving_rec")


def load_rows(csv_text: str | None, pos: str) -> list[Row]:
    rows: list[Row] = []
    if not csv_text:
        return rows
    for raw in csv.DictReader(io.StringIO(csv_text)):
        try:
            week = int(raw["WK"])
        except (KeyError, ValueError):
            continue
        stats: dict[str, float] = {}
        for key, value in raw.items():
            if key in ("NAME", "TEAM", "POS", "OPP", "WK", "RK") or value is None or value.strip() == "":
                continue
            try:
                stats[key.lower()] = float(value)
            except ValueError:
                continue
        name = (raw.get("NAME") or "").strip()
        rows.append(Row(name, normalize_player_name(name), (raw.get("TEAM") or "").strip(), (raw.get("OPP") or "").strip(), week, pos, stats))
    return rows


def _latest_first(detail: list[str]) -> list[str]:
    """Hover lists read newest game first (every line carries "W<week>")."""
    def week(line: str) -> int:
        m = re.search(r"\bW(\d+)\b", line)
        return int(m.group(1)) if m else 0

    return sorted(detail, key=week, reverse=True)


def _chip(family: str, up: bool, text: str, detail: list[str] | None = None) -> SignalChip:
    return SignalChip(family=family, polarity="up" if up else "down", text=text, detail=_latest_first(detail or []))  # type: ignore[arg-type]


def _num(x: float) -> str:
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


class Context:
    def __init__(self, rows_by_pos: dict[str, list[Row]], vegas: VegasLinesSnapshot | None, statuses: dict[str, str], week: int, last_x: int, th: dict[str, float], opponent_scope: str = "last"):
        self.week, self.last_x, self.th, self.statuses = week, last_x, th, statuses
        self.opponent_scope = opponent_scope
        self.first_week = max(1, week - last_x)
        self.rows = {p: [r for r in rows if r.week < week] for p, rows in rows_by_pos.items()}
        self.window = {p: [r for r in rows if r.week >= self.first_week] for p, rows in self.rows.items()}
        self.last_week = max((r.week for rs in self.rows.values() for r in rs), default=0)

        self.by_player: dict[tuple[str, str], list[Row]] = defaultdict(list)
        self.by_team: dict[tuple[str, str], list[Row]] = defaultdict(list)
        for p, rs in self.window.items():
            for r in rs:
                self.by_player[(p, r.norm)].append(r)
                self.by_team[(p, r.team)].append(r)
        for lst in self.by_player.values():
            lst.sort(key=lambda r: r.week)

        # opponent history: last X weeks (default) or the whole season
        opp_rows = self.window if opponent_scope == "last" else self.rows
        self.vs_opp: dict[str, dict[str, list[Row]]] = {p: defaultdict(list) for p in POSITIONS}
        for p, rs in opp_rows.items():
            for r in rs:
                self.vs_opp[p][r.opp].append(r)

        team_rb: dict[tuple[str, int], float] = defaultdict(float)
        for r in self.window["RB"]:
            team_rb[(r.team, r.week)] += r.g("rushing_att")
        self.team_rb_carries = team_rb

        # points scored by an offense = OPP_PTS on the DST row of the defense that faced it
        self.scored: dict[str, list[float]] = defaultdict(list)
        self.allowed: dict[str, list[float]] = defaultdict(list)
        # (week, other team, points) per game, for the hover lists
        self.scored_games: dict[str, list[tuple[int, str, float]]] = defaultdict(list)
        self.allowed_games: dict[str, list[tuple[int, str, float]]] = defaultdict(list)
        for r in self.rows["DST"]:
            if "opp_pts" in r.s:
                if opponent_scope != "last" or r.week >= self.first_week:
                    self.allowed[r.team].append(r.s["opp_pts"])
                    self.allowed_games[r.team].append((r.week, r.opp, r.s["opp_pts"]))
                if r.week >= self.first_week:
                    self.scored[r.opp].append(r.s["opp_pts"])
                    self.scored_games[r.opp].append((r.week, r.team, r.s["opp_pts"]))

        self.allowed_pg: dict[str, dict[str, float]] = {}
        for p in ("QB", "RB", "WR", "TE"):
            per: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
            for r in opp_rows[p]:
                per[r.opp][r.week] += r.g("fpts")
            avg = {d: mean(w.values()) for d, w in per.items() if len(w) >= int(th["min_games"]) - 1}
            self.allowed_pg[p] = avg
        self.implied: dict[str, tuple[float | None, float | None]] = {}
        for g in (vegas.games if vegas else []):
            total = g.current.over_under
            if g.home_team:
                self.implied[g.home_team] = (g.current.home_implied_total, total)
            if g.away_team:
                self.implied[g.away_team] = (g.current.away_implied_total, total)

    def player_rows(self, pos: str, p: OwnershipPlayer) -> list[Row]:
        if pos == "DST":
            return sorted(self.by_team.get(("DST", p.team), []), key=lambda r: r.week)
        return self.by_player.get((pos, normalize_player_name(p.player)), [])

    def opp_starting_qbs(self, team: str) -> list[Row]:
        best: dict[int, Row] = {}
        for r in self.window["QB"]:
            if r.team == team and (r.week not in best or r.g("passing_att") > best[r.week].g("passing_att")):
                best[r.week] = r
        return [best[w] for w in sorted(best)]


# ---------------------------------------------------------------- usage rules

def _boom(rows: list[Row], th, n: int) -> list[SignalChip]:
    pts = [r.g("fpts") for r in rows]
    c = sum(1 for x in pts if x >= th["boom_pts"])
    if c >= th["boom_games"]:
        return [_chip("usage", True, f"{c} games of {_num(th['boom_pts'])}+ DK pts in last {n}", [f"W{r.week}: {_num(r.g('fpts'))} pts" for r in rows if r.g("fpts") >= th["boom_pts"]])]
    return []


def _streak(rows: list[Row], key, floor: float, k: int) -> bool:
    return len(rows) >= k and all(key(r) >= floor for r in rows[-k:])


def _trend(rows: list[Row], key, min_level: float, label: str) -> list[SignalChip]:
    if len(rows) < 3:
        return []
    last, prev = key(rows[-1]), mean(key(r) for r in rows[:-1])
    seq = ", ".join(_num(key(r)) for r in rows)
    if prev >= min_level * 0.5 and last >= max(prev * 1.5, min_level):
        return [_chip("usage", True, f"{label} up: {seq}")]
    if prev >= min_level and last <= prev * 0.5:
        return [_chip("usage", False, f"{label} down: {seq}")]
    return []


def usage_rb(rows: list[Row], team_carries, p: OwnershipPlayer, th, n: int) -> list[SignalChip]:
    out: list[SignalChip] = []
    if len(rows) < 2:
        return out
    carries = sum(r.g("rushing_att") for r in rows)
    team = sum(team_carries.get((r.team, r.week), 0.0) for r in rows)
    if team >= 20:
        share = 100 * carries / team
        if share >= th["rb_carry_share"]:
            out.append(_chip("usage", True, f"Carry share {_num(share)}% last {len(rows)}"))
        elif share < 40 and p.salary >= 4500:
            out.append(_chip("usage", False, f"Carry share {_num(share)}% (committee) at ${p.salary:,}"))
    k = int(th["streak_games"])
    if _streak(rows, lambda r: r.touches, th["rb_touch_streak"], k):
        out.append(_chip("usage", True, f"{_num(th['rb_touch_streak'])}+ touches in each of last {k}"))
    tgt = [r.s["tgt_share"] for r in rows if "tgt_share" in r.s]
    if tgt and mean(tgt) >= th["rb_tgt_share"]:
        out.append(_chip("usage", True, f"Target share {_num(mean(tgt))}% last {len(tgt)}"))
    out += _trend(rows, lambda r: r.g("rushing_att"), 8, "Carries")
    out += _boom(rows, th, n)
    return out


def usage_pass_catcher(rows: list[Row], p: OwnershipPlayer, th, n: int) -> list[SignalChip]:
    out: list[SignalChip] = []
    if len(rows) < 2:
        return out
    is_te = p.position == "TE"
    share_floor = th["te_tgt_share" if is_te else "wr_tgt_share"]
    tpg_floor = th["te_tgts_pg" if is_te else "wr_tgts_pg"]
    tgt = [r.s["tgt_share"] for r in rows if "tgt_share" in r.s]
    if tgt:
        s = mean(tgt)
        if s >= share_floor:
            out.append(_chip("usage", True, f"Target share {_num(s)}% last {len(tgt)}"))
        elif s < 12 and p.salary >= 5500:
            out.append(_chip("usage", False, f"Target share {_num(s)}% at ${p.salary:,}"))
    tpg = mean(r.g("receiving_tgts") for r in rows)
    if tpg >= tpg_floor:
        out.append(_chip("usage", True, f"{_num(tpg)} targets per game"))
    k = int(th["streak_games"])
    if _streak(rows, lambda r: r.g("receiving_yds"), th["rec_yards_streak"], k):
        out.append(_chip("usage", True, f"{_num(th['rec_yards_streak'])}+ receiving yds in each of last {k}"))
    out += _trend(rows, lambda r: r.g("receiving_tgts"), 6, "Targets")
    out += _boom(rows, th, n)
    return out


def usage_qb(rows: list[Row], th, n: int) -> list[SignalChip]:
    out: list[SignalChip] = []
    if len(rows) < 3:
        return out
    c = sum(1 for r in rows if r.g("passing_att") >= th["qb_att_floor"])
    if c / len(rows) >= 0.7:
        out.append(_chip("usage", True, f"{_num(th['qb_att_floor'])}+ attempts in {c} of {len(rows)}"))
    elif mean(r.g("passing_att") for r in rows) < 28:
        out.append(_chip("usage", False, f"Averages {_num(mean(r.g('passing_att') for r in rows))} pass attempts"))
    ry = mean(r.g("rushing_yds") for r in rows)
    if ry >= th["qb_rush_yds"]:
        out.append(_chip("usage", True, f"Rushes {_num(ry)} yds per game"))
    out += _boom(rows, th, n)
    return out


def usage_dst(rows: list[Row], th) -> list[SignalChip]:
    out: list[SignalChip] = []
    if len(rows) < 3:
        return out
    sacks = mean(r.g("def_sck") for r in rows)
    if sacks >= th["dst_sacks_pg"]:
        out.append(_chip("usage", True, f"Sacks {_num(sacks)}/game last {len(rows)}", [f"W{r.week} vs {r.opp}: {_num(r.g('def_sck'))} sacks" for r in rows]))
    tk = mean(r.g("def_int") + r.g("fr") for r in rows)
    if tk >= th["dst_takeaways_pg"]:
        out.append(_chip("usage", True, f"Takeaways {_num(tk)}/game last {len(rows)}", [f"W{r.week} vs {r.opp}: {_num(r.g('def_int'))} INT, {_num(r.g('fr'))} FR" for r in rows]))
    return out


# -------------------------------------------------------------- matchup rules

def _allowed_by_week(rows: list[Row]) -> list[str]:
    """One line per game: the position's total FPTS against this defense and its top scorers."""
    by_week: dict[int, list[Row]] = defaultdict(list)
    for r in rows:
        by_week[r.week].append(r)
    lines = []
    for week in sorted(by_week):
        group = sorted(by_week[week], key=lambda r: -r.g("fpts"))
        total = sum(r.g("fpts") for r in group)
        who = ", ".join(f"{r.name} {_num(r.g('fpts'))}" for r in group[:3] if r.g("fpts") > 0)
        lines.append(f"W{week} vs {group[0].team}: {_num(total)} pts ({who})" if who else f"W{week} vs {group[0].team}: {_num(total)} pts")
    return lines


def matchup_rules(ctx: Context, p: OwnershipPlayer) -> list[SignalChip]:
    th, pos, opp = ctx.th, p.position, p.opponent
    out: list[SignalChip] = []
    if pos == "DST":
        return out
    avg = ctx.allowed_pg.get(pos, {})
    week_lines = _allowed_by_week(ctx.vs_opp[pos].get(opp, []))
    if opp in avg:
        ranked = sorted(avg, key=lambda d: -avg[d])
        rank, n_def, top = ranked.index(opp) + 1, len(ranked), int(th["rank_top_n"])
        if rank <= top:
            out.append(_chip("matchup", True, f"{opp} allows #{rank} most FPTS to {pos} ({_num(avg[opp])}/game)", week_lines))
        elif rank > n_def - top:
            out.append(_chip("matchup", False, f"{opp} allows #{n_def - rank + 1} fewest FPTS to {pos} ({_num(avg[opp])}/game)", week_lines))
    rows = ctx.vs_opp[pos].get(opp, [])
    games = sorted({r.week for r in rows})
    g = len(games)
    if g < th["min_games"]:
        return out
    share = th["matchup_share"] / 100
    if pos == "RB":
        best = {}
        for r in rows:
            total = r.g("rushing_yds") + r.g("receiving_yds")
            if r.week not in best or total > best[r.week][0]:
                best[r.week] = (total, r)
        big = [(w, t, r) for w, (t, r) in sorted(best.items()) if t >= th["opp_rb_big_yds"]]
        det = [f"{r.name} W{w} ({_num(t)} total yds)" for w, t, r in big]
        if len(big) / g >= share:
            out.append(_chip("matchup", True, f"Lead RB topped {_num(th['opp_rb_big_yds'])} total yds in {len(big)} of {g} vs {opp}", det))
        elif (g - len(big)) / g >= 0.85:
            out.append(_chip("matchup", False, f"{opp} held lead RB under {_num(th['opp_rb_big_yds'])} total yds in {g - len(big)} of {g}"))
    elif pos == "WR":
        big = [r for r in rows if r.g("fpts") >= th["opp_wr_big_pts"]]
        det = [f"{r.name} W{r.week} ({_num(r.g('fpts'))} pts)" for r in sorted(big, key=lambda r: r.week)]
        if len(big) / g >= 1.0:
            out.append(_chip("matchup", True, f"{len(big)} WRs with {_num(th['opp_wr_big_pts'])}+ DK pts vs {opp} in {g} games", det))
        elif len(big) <= 1 and g >= 5:
            out.append(_chip("matchup", False, f"Only {len(big)} WR with {_num(th['opp_wr_big_pts'])}+ DK pts vs {opp} in {g} games", det))
    elif pos == "TE":
        big = [r for r in rows if r.g("receiving_yds") >= th["opp_te_big_yds"] and r.g("receiving_td") >= 1]
        det = [f"{r.name} W{r.week} ({_num(r.g('receiving_yds'))} yds, TD)" for r in sorted(big, key=lambda r: r.week)]
        if len(big) >= 2:
            out.append(_chip("matchup", True, f"{len(big)} TEs with {_num(th['opp_te_big_yds'])}+ yds and a TD vs {opp}", det))
    elif pos == "QB":
        starters: dict[int, Row] = {}
        for r in rows:
            if r.week not in starters or r.g("passing_att") > starters[r.week].g("passing_att"):
                starters[r.week] = r
        qbs = [starters[w] for w in sorted(starters)]
        big = [r for r in qbs if r.g("passing_yds") + r.g("rushing_yds") >= th["opp_qb_big_yds"]]
        td2 = [r for r in qbs if r.g("passing_td") >= 2]
        held = [r for r in qbs if r.g("passing_yds") < th["opp_qb_held_yds"]]
        if len(big) / g >= share:
            out.append(_chip("matchup", True, f"Opposing QBs topped {_num(th['opp_qb_big_yds'])} total yds in {len(big)} of {g}", [f"{r.name} W{r.week} ({_num(r.g('passing_yds') + r.g('rushing_yds'))} yds)" for r in big]))
        if len(td2) / g >= 0.75:
            out.append(_chip("matchup", True, f"Opposing QBs threw 2+ TD in {len(td2)} of {g}", [f"{r.name} W{r.week} ({_num(r.g('passing_td'))} TD)" for r in td2]))
        if len(held) / g >= 0.75:
            out.append(_chip("matchup", False, f"{opp} held QBs under {_num(th['opp_qb_held_yds'])} pass yds in {len(held)} of {g}", [f"{r.name} W{r.week} ({_num(r.g('passing_yds'))} yds)" for r in held]))
    return out


# ------------------------------------------------------------- game environment

def _games(items: list[tuple[int, str, float]], label: str) -> list[str]:
    return [f"W{w} vs {o}: {_num(pts)} {label}" for w, o, pts in sorted(items)]


def game_rules(ctx: Context, p: OwnershipPlayer) -> list[SignalChip]:
    th, out = ctx.th, []
    imp, total = ctx.implied.get(p.team, (None, None))
    opp_imp, _ = ctx.implied.get(p.opponent, (None, None))
    if p.position == "DST":
        if opp_imp is not None:
            if opp_imp <= th["implied_low"]:
                out.append(_chip("game", True, f"Opponent implied {_num(opp_imp)}"))
            elif opp_imp >= th["implied_high"]:
                out.append(_chip("game", False, f"Opponent implied {_num(opp_imp)}"))
        opp_scored = ctx.scored.get(p.opponent, [])
        if len(opp_scored) >= 3:
            m = mean(opp_scored)
            if m <= 17:
                out.append(_chip("game", True, f"{p.opponent} scores {_num(m)}/game last {len(opp_scored)}", _games(ctx.scored_games[p.opponent], "pts")))
            elif m >= 27:
                out.append(_chip("game", False, f"{p.opponent} scores {_num(m)}/game last {len(opp_scored)}", _games(ctx.scored_games[p.opponent], "pts")))
        qbs = ctx.opp_starting_qbs(p.opponent)
        if len(qbs) >= 3:
            sck, ints = mean(r.g("sck") for r in qbs), mean(r.g("int") for r in qbs)
            if sck >= th["dst_sacks_pg"]:
                out.append(_chip("matchup", True, f"{p.opponent} QB sacked {_num(sck)}/game last {len(qbs)}", [f"W{r.week} vs {r.opp}: {_num(r.g('sck'))} sacks ({r.name})" for r in qbs]))
            if ints >= 1:
                out.append(_chip("matchup", True, f"{p.opponent} QB throws {_num(ints)} INT/game last {len(qbs)}", [f"W{r.week} vs {r.opp}: {_num(r.g('int'))} INT ({r.name})" for r in qbs]))
        return out
    if imp is not None:
        if imp >= th["implied_high"]:
            out.append(_chip("game", True, f"Implied {_num(imp)}"))
        elif imp <= th["implied_low"]:
            out.append(_chip("game", False, f"Implied {_num(imp)}"))
    if total is not None:
        if total >= th["total_high"]:
            out.append(_chip("game", True, f"Game total {_num(total)}"))
        elif total <= th["total_low"]:
            out.append(_chip("game", False, f"Game total {_num(total)}"))
    allowed = ctx.allowed.get(p.opponent, [])
    if len(allowed) >= th["min_games"]:
        c = sum(1 for x in allowed if x >= th["opp_pts_allowed"])
        if c / len(allowed) >= 0.7:
            out.append(_chip("game", True, f"{p.opponent} allowed {_num(th['opp_pts_allowed'])}+ in {c} of {len(allowed)}", _games(ctx.allowed_games[p.opponent], "pts allowed")))
    scored = ctx.scored.get(p.team, [])
    if len(scored) >= 3 and mean(scored) <= 17:
        out.append(_chip("game", False, f"{p.team} scores {_num(mean(scored))}/game last {len(scored)}", _games(ctx.scored_games[p.team], "pts")))
    return out


# --------------------------------------------------------------------- role

def role_rules(ctx: Context, p: OwnershipPlayer) -> list[SignalChip]:
    out: list[SignalChip] = []
    if p.status and p.status not in OUT_STATUSES:
        out.append(_chip("role", False, f"Listed {p.status}"))
    if p.position not in ("RB", "WR", "TE"):
        return out
    me = normalize_player_name(p.player)
    groups = [("RB",)] if p.position == "RB" else [("WR", "TE")]
    for pos in groups[0]:
        seen = set()
        for r in ctx.by_team.get((pos, p.team), []):
            if r.norm == me or r.norm in seen:
                continue
            seen.add(r.norm)
            if ctx.statuses.get(r.norm) not in OUT_STATUSES | {"D"}:
                continue
            rows = ctx.by_player.get((pos, r.norm), [])
            if pos == "RB" and mean(x.touches for x in rows) >= 10:
                out.append(_chip("role", True, f"{r.name} out ({_num(mean(x.touches for x in rows))} touches/game)"))
            elif pos in ("WR", "TE"):
                sh = [x.s["tgt_share"] for x in rows if "tgt_share" in x.s]
                if sh and mean(sh) >= 15:
                    out.append(_chip("role", True, f"{r.name} out ({_num(mean(sh))}% targets)"))
    return out


# -------------------------------------------------------------------- build

def build_player_signals(players: list[OwnershipPlayer], ctx: Context) -> list[SignalPlayer]:
    th = ctx.th
    result: list[SignalPlayer] = []
    for p in players:
        if p.position not in POSITIONS or (p.status in SKIP_STATUSES):
            continue
        rows = ctx.player_rows(p.position, p)
        n = len(rows)
        chips: list[SignalChip] = []
        if p.position == "RB":
            chips += usage_rb(rows, ctx.team_rb_carries, p, th, ctx.last_x)
        elif p.position in ("WR", "TE"):
            chips += usage_pass_catcher(rows, p, th, ctx.last_x)
        elif p.position == "QB":
            chips += usage_qb(rows, th, ctx.last_x)
        else:
            chips += usage_dst(rows, th)
        chips += matchup_rules(ctx, p)
        chips += game_rules(ctx, p)
        chips += role_rules(ctx, p)

        pts = mean(r.g("fpts") for r in rows) if rows else None
        if pts is not None and p.salary and p.position != "DST" and pts >= 8 and pts / (p.salary / 1000) >= th["value_pts_per_k"]:
            chips.append(_chip("price", True, f"Last {n} avg {_num(pts)} pts = {pts / (p.salary / 1000):.1f}x at ${p.salary:,}"))
        usage_ups = sum(1 for c in chips if c.family == "usage" and c.polarity == "up")
        if p.ownership_pct is not None and p.ownership_pct <= th["low_own"] and usage_ups >= th["lowown_min_usage"]:
            chips.append(_chip("price", True, f"Own {_num(p.ownership_pct)}% with {usage_ups} usage signals"))

        up = sum(1 for c in chips if c.polarity == "up")
        down = len(chips) - up
        result.append(
            SignalPlayer(
                player=p.player, position=p.position, team=p.team, opponent=p.opponent, salary=p.salary,
                ownership_pct=p.ownership_pct, status=p.status,
                pts_last_x=round(pts, 1) if pts is not None else None, games_used=n,
                up=up, down=down, net=up - down, signals=chips,
            )
        )
    result.sort(key=lambda s: (-s.net, -s.up, -s.salary))
    return result
