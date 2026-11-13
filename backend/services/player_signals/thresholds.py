"""Editable thresholds for the Player Pool Signals rules. Each entry is
(key, label, group, default); the tab shows them in a collapsed panel and sends
overrides back as JSON. Every rule in engine.py reads its cut-off from here."""

from __future__ import annotations

from backend.schemas.player_signals.player_signals import ThresholdInfo

_SPEC: list[tuple[str, str, str, float]] = [
    ("rb_carry_share", "Carry share at least (%)", "RB", 55),
    ("rb_touch_streak", "Touch streak (touches)", "RB", 25),
    ("rb_tgt_share", "Target share at least (%)", "RB", 15),
    ("opp_rb_big_yds", "Opp RB big game (total yds)", "RB", 100),
    ("wr_tgt_share", "WR target share at least (%)", "WR / TE", 24),
    ("te_tgt_share", "TE target share at least (%)", "WR / TE", 18),
    ("wr_tgts_pg", "WR targets per game at least", "WR / TE", 8),
    ("te_tgts_pg", "TE targets per game at least", "WR / TE", 6),
    ("rec_yards_streak", "Receiving yards streak (yds)", "WR / TE", 100),
    ("opp_wr_big_pts", "Opp WR big game (DK pts)", "WR / TE", 20),
    ("opp_te_big_yds", "Opp TE big game (yds + TD)", "WR / TE", 59),
    ("qb_att_floor", "QB attempts floor", "QB / DST", 36),
    ("qb_rush_yds", "QB rush yards per game at least", "QB / DST", 25),
    ("opp_qb_big_yds", "Opp QB big game (total yds)", "QB / DST", 300),
    ("opp_qb_held_yds", "Opp QB held under (pass yds)", "QB / DST", 220),
    ("dst_sacks_pg", "DST sacks per game at least", "QB / DST", 3),
    ("dst_takeaways_pg", "DST takeaways per game at least", "QB / DST", 1.5),
    ("streak_games", "Streak games", "All", 2),
    ("boom_pts", "Boom game (DK pts)", "All", 25),
    ("boom_games", "Boom games needed", "All", 2),
    ("implied_high", "Implied total high", "All", 24),
    ("implied_low", "Implied total low", "All", 18),
    ("total_high", "Game total high", "All", 48),
    ("total_low", "Game total low", "All", 41),
    ("opp_pts_allowed", "Opp allowed points (per game)", "All", 24),
    ("rank_top_n", "Matchup rank cutoff (top N)", "All", 8),
    ("ppg_rank_top_n", "Points-per-game rank cutoff (top N in position)", "All", 10),
    ("matchup_share", "Opponent history share of games (%)", "All", 60),
    ("min_games", "Min games for opponent history", "All", 4),
    ("low_own", "Low ownership at most (%)", "All", 10),
    ("lowown_min_usage", "Usage signals for low-own chip", "All", 3),
    ("value_pts_per_k", "Value (pts per $1K) at least", "All", 3),
]

DEFAULTS: dict[str, float] = {key: float(default) for key, _l, _g, default in _SPEC}


def resolve(overrides: dict[str, float] | None) -> dict[str, float]:
    values = dict(DEFAULTS)
    for key, value in (overrides or {}).items():
        if key in values:
            values[key] = float(value)
    return values


def describe(values: dict[str, float]) -> list[ThresholdInfo]:
    return [
        ThresholdInfo(key=key, label=label, group=group, value=values[key], default=float(default))
        for key, label, group, default in _SPEC
    ]
