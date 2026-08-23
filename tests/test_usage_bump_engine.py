from backend.schemas.depth_charts.snapshot import Player, Snapshot, Team
from backend.services.usage_bump.engine import compute_usage_bumps


def make_snapshot(teams: list[Team]) -> Snapshot:
    return Snapshot(scraped_at="2026-08-17T08:00:00-04:00", source_url="https://example.com", teams=teams)


# Small matrix covering just what these tests need -- same shape/semantics
# as the real config/player-out-settings.json (see scoring_matrix_repo.py /
# engine.py docstrings): (0,) is the sentinel for "nobody else in the
# usage-bump list is out."
MATRIX = {
    (0,): {1: 1.0, 2: 0.5, 3: 0.25, 4: 0, 5: 0},
    (1,): {1: 0, 2: 1.0, 3: 0.5, 4: 0.25, 5: 0},
    (2,): {1: 1.0, 2: 0, 3: 0.5, 4: 0.25, 5: 0},
}


def test_curated_list_base_case_uses_sentinel_row():
    team = Team(
        team_abbrev="CAR",
        team_name="Carolina Panthers",
        positions={
            "WR": [
                Player(player="Jalen Coker", status="IR"),
                Player(player="Tetairoa McMillan", status=None),
                Player(player="Xavier Legette", status=None),
            ]
        },
    )
    usage_bump_players = {("CAR", "Jalen Coker"): ["Tetairoa McMillan", "Xavier Legette"]}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), usage_bump_players, {}, MATRIX)
    by_player = {o.player: o for o in usage_bumps}

    assert by_player["Tetairoa McMillan"].bump_score == 1.0
    assert by_player["Xavier Legette"].bump_score == 0.5
    assert len(by_player["Tetairoa McMillan"].causes) == 1
    cause = by_player["Tetairoa McMillan"].causes[0]
    assert cause.player == "Jalen Coker"
    assert cause.status == "IR"
    assert cause.weight == 1.0
    # Jalen Coker's own real role label -- WR1, not a list position.
    assert (cause.position, cause.rank) == ("WR", 1)
    # Resolved via the curated list, not the position-settings fallback.
    assert cause.source == "curated"
    assert cause.source_role_label is None
    assert cause.source_role_positions is None
    # Sentinel match -- nobody else in the list is out.
    assert cause.player_out_depths == [0]
    # Full resolved list, matched row's weight applied to every position
    # in it -- not just McMillan's own slot -- plus each member's own
    # real position/rank (their real WR2/WR3 depth-chart slot, not their
    # list position) and current status.
    assert [(e.depth, e.player, e.position, e.rank, e.status, e.weight) for e in cause.usage_bump_list] == [
        (1, "Tetairoa McMillan", "WR", 2, None, 1.0),
        (2, "Xavier Legette", "WR", 3, None, 0.5),
    ]
    # Xavier Legette's own cause carries the exact same shared list/combo.
    legette_cause = by_player["Xavier Legette"].causes[0]
    assert legette_cause.player_out_depths == [0]
    assert [(e.depth, e.player, e.position, e.rank, e.status, e.weight) for e in legette_cause.usage_bump_list] == [
        (1, "Tetairoa McMillan", "WR", 2, None, 1.0),
        (2, "Xavier Legette", "WR", 3, None, 0.5),
    ]


def test_curated_list_member_also_out_uses_combo_row_and_gets_no_credit():
    team = Team(
        team_abbrev="CAR",
        team_name="Carolina Panthers",
        positions={
            "WR": [
                Player(player="Jalen Coker", status="IR"),
                Player(player="Tetairoa McMillan", status="Q"),  # also out
                Player(player="Xavier Legette", status=None),
            ]
        },
    )
    usage_bump_players = {("CAR", "Jalen Coker"): ["Tetairoa McMillan", "Xavier Legette"]}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), usage_bump_players, {}, MATRIX)
    by_player = {o.player: o for o in usage_bumps}

    assert "Tetairoa McMillan" not in by_player
    # McMillan (list position 1) is out -> combo (1,) row applies: list position 2 (Legette) = 1.0
    assert by_player["Xavier Legette"].bump_score == 1.0
    cause = by_player["Xavier Legette"].causes[0]
    assert cause.player_out_depths == [1]
    # The full list still includes McMillan (weight 0 under this row, and
    # withheld anyway since he's out -- his status shows up here too)
    # alongside Legette's own weight.
    assert [(e.depth, e.player, e.position, e.rank, e.status, e.weight) for e in cause.usage_bump_list] == [
        (1, "Tetairoa McMillan", "WR", 2, "Q", 0),
        (2, "Xavier Legette", "WR", 3, None, 1.0),
    ]


def test_no_curated_entry_falls_back_to_position_settings():
    team = Team(
        team_abbrev="ARI",
        team_name="Arizona Cardinals",
        positions={
            "RB": [
                Player(player="James Conner", status="IR"),
                Player(player="Trey Benson", status=None),
            ],
            "WR": [Player(player="Marvin Harrison", status=None)],
        },
    )
    position_settings = {"RB1": ["RB2", "WR1"]}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), {}, position_settings, MATRIX)
    by_player = {o.player: o for o in usage_bumps}

    assert by_player["Trey Benson"].bump_score == 1.0  # list position 1
    assert by_player["Marvin Harrison"].bump_score == 0.5  # list position 2

    cause = by_player["Trey Benson"].causes[0]
    assert (cause.position, cause.rank) == ("RB", 1)  # James Conner's own role label: RB1
    assert cause.source == "position-settings"
    assert cause.source_role_label == "RB1"
    assert cause.source_role_positions == ["RB2", "WR1"]  # raw config value, unresolved role labels


def test_multi_listed_player_prefers_offensive_fantasy_position():
    # A two-way player (or a WR also listed as a punt returner) can appear
    # under more than one position group on the same team's depth chart.
    # _resolve_role_label always matches correctly against the intended
    # group (team.positions["WR"] here), but the *display* location for
    # that name must prefer the offensive fantasy listing (WR) over
    # whatever non-fantasy group ("LCB") also lists them -- regardless of
    # which one comes later in the team's positions dict.
    team = Team(
        team_abbrev="JAX",
        team_name="Jacksonville Jaguars",
        positions={
            "WR": [
                Player(player="WR1Player", status=None),
                Player(player="WR2Player", status=None),
                Player(player="Jakobi Meyers", status="Q"),
                Player(player="Travis Hunter", status=None),  # WR4
            ],
            # Comes after "WR" -- would clobber Travis Hunter's location
            # if _build_location didn't prefer offensive fantasy positions.
            "LCB": [Player(player="Travis Hunter", status=None)],
        },
    )
    position_settings = {"WR3": ["WR4"]}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), {}, position_settings, MATRIX)
    by_player = {o.player: o for o in usage_bumps}

    # The UsageBump itself resolves to the offensive fantasy position...
    assert (by_player["Travis Hunter"].position, by_player["Travis Hunter"].rank) == ("WR", 4)
    # ...and so does the usage_bump_list entry inside the cause.
    entry = by_player["Travis Hunter"].causes[0].usage_bump_list[0]
    assert (entry.position, entry.rank) == ("WR", 4)


def test_curated_takes_priority_over_position_settings():
    team = Team(
        team_abbrev="ARI",
        team_name="Arizona Cardinals",
        positions={
            "RB": [Player(player="Trigger", status="IR"), Player(player="RB2Player", status=None)],
            "WR": [Player(player="CuratedWR", status=None)],
        },
    )
    usage_bump_players = {("ARI", "Trigger"): ["CuratedWR"]}
    position_settings = {"RB1": ["RB2Player"]}  # would apply if curated weren't checked first

    usage_bumps = compute_usage_bumps(make_snapshot([team]), usage_bump_players, position_settings, MATRIX)
    by_player = {o.player: o for o in usage_bumps}

    assert "RB2Player" not in by_player
    assert by_player["CuratedWR"].bump_score == 1.0


def test_role_with_no_settings_entry_produces_no_bump():
    team = Team(
        team_abbrev="ARI",
        team_name="Arizona Cardinals",
        positions={"RB": [Player(player="James Conner", status="IR"), Player(player="Trey Benson", status=None)]},
    )
    # No curated entry, no position_settings entry for RB1 at all.
    usage_bumps = compute_usage_bumps(make_snapshot([team]), {}, {}, MATRIX)

    assert usage_bumps == []


def test_unresolvable_role_label_is_skipped_not_fatal():
    team = Team(
        team_abbrev="ARI",
        team_name="Arizona Cardinals",
        positions={
            "RB": [Player(player="James Conner", status="IR"), Player(player="Trey Benson", status=None)],
            # No WR entries at all -- "WR1" below won't resolve to anyone.
        },
    )
    position_settings = {"RB1": ["WR1", "RB2"]}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), {}, position_settings, MATRIX)
    by_player = {o.player: o for o in usage_bumps}

    # WR1 dropped entirely (unresolvable) -- Trey Benson shifts up to list
    # position 1 rather than staying at position 2.
    assert by_player["Trey Benson"].bump_score == 1.0


def test_unconfigured_combo_produces_no_bump_for_that_trigger():
    team = Team(
        team_abbrev="ARI",
        team_name="Arizona Cardinals",
        positions={
            "RB": [
                Player(player="A", status="IR"),
                Player(player="B", status="Q"),  # also out -- list position 1
                Player(player="C", status=None),  # healthy -- list position 2
                Player(player="D", status="D"),  # also out -- list position 3
            ]
        },
    )
    position_settings = {"RB1": ["RB2", "RB3", "RB4"]}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), {}, position_settings, MATRIX)

    # Out list-positions are (1, 3) -- not a key in MATRIX -- no row, so no
    # bump for anyone in this cluster, including the healthy C.
    assert usage_bumps == []


def test_contributions_from_multiple_triggers_stack():
    team = Team(
        team_abbrev="ARI",
        team_name="Arizona Cardinals",
        positions={
            "RB": [Player(player="RB1Player", status="IR")],
            "QB": [Player(player="QB1Player", status="D")],
            "WR": [Player(player="SharedWR", status=None)],
        },
    )
    usage_bump_players = {("ARI", "RB1Player"): ["SharedWR"]}
    # position_settings values are role labels, resolved via the team's
    # real depth chart -- SharedWR is this team's only (so rank-1) WR.
    position_settings = {"QB1": ["WR1"]}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), usage_bump_players, position_settings, MATRIX)

    assert len(usage_bumps) == 1
    shared = usage_bumps[0]
    assert shared.player == "SharedWR"
    assert shared.bump_score == 2.0  # 1.0 from each trigger's sentinel-row contribution
    assert {c.player for c in shared.causes} == {"RB1Player", "QB1Player"}


def test_usage_bump_list_capped_at_five():
    team = Team(
        team_abbrev="ARI",
        team_name="Arizona Cardinals",
        positions={
            "WR": [
                Player(player="Trigger", status="IR"),
                Player(player="B1", status=None),
                Player(player="B2", status=None),
                Player(player="B3", status=None),
                Player(player="B4", status=None),
                Player(player="B5", status=None),
                Player(player="B6", status=None),
            ]
        },
    )
    usage_bump_players = {("ARI", "Trigger"): ["B1", "B2", "B3", "B4", "B5", "B6"]}
    matrix = {(0,): {1: 1, 2: 1, 3: 1, 4: 1, 5: 1}}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), usage_bump_players, {}, matrix)
    by_player = {o.player: o for o in usage_bumps}

    assert set(by_player.keys()) == {"B1", "B2", "B3", "B4", "B5"}


def test_results_sorted_by_bump_score_descending():
    team = Team(
        team_abbrev="ARI",
        team_name="Arizona Cardinals",
        positions={
            "RB": [
                Player(player="Trigger", status="IR"),
                Player(player="Big", status=None),
                Player(player="Small", status=None),
            ]
        },
    )
    usage_bump_players = {("ARI", "Trigger"): ["Big", "Small"]}

    usage_bumps = compute_usage_bumps(make_snapshot([team]), usage_bump_players, {}, MATRIX)

    assert [o.player for o in usage_bumps] == ["Big", "Small"]
    assert [o.bump_score for o in usage_bumps] == [1.0, 0.5]
