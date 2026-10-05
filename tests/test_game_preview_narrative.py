from backend.schemas.game_preview.game_preview import (
    GamePreviewDstMatchup,
    GamePreviewPaceTrend,
    GamePreviewPlayer,
    GamePreviewPlayerTag,
    GamePreviewPositionalMatchup,
    GamePreviewTeamFactors,
    GamePreviewTeamSide,
    GamePreviewVegas,
)
from backend.services.game_preview.game_preview_narrative import build_game_narrative

LABEL = "LAC @ DEN"


def _side(
    team,
    is_home,
    dst_matchup=None,
    players=None,
    pace_trend=None,
    exploitable_positions=None,
    projected_ownership_pct=None,
):
    return GamePreviewTeamSide(
        team=team,
        is_home=is_home,
        team_factors=GamePreviewTeamFactors(),
        dst_matchup=dst_matchup,
        players=players or [],
        pace_trend=pace_trend,
        exploitable_positions=exploitable_positions or [],
        projected_ownership_pct=projected_ownership_pct,
    )


def _section(sections, label):
    return next(s for s in sections if s.label == label)


def test_no_signals_gives_fallback_section():
    away = _side("LAC", False)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    assert len(sections) == 1
    assert sections[0].label is None
    assert sections[0].entries == [f"No notable Vegas, O vs D Line matchup, or player-tag signals yet for {LABEL}."]


def test_vegas_section_with_implied_totals():
    away = _side("LAC", False)
    home = _side("DEN", True)
    vegas = GamePreviewVegas(over_under=45.5, away_implied_total=22.5, home_implied_total=23.0, kickoff_label="Sun 4:25pm")
    sections = build_game_narrative(LABEL, away, home, vegas)
    assert len(sections) == 1
    assert sections[0].label is None
    assert sections[0].entries == ["45.5 O/U (LAC 22.5 - DEN 23)"]


def test_vegas_section_without_implied_totals():
    away = _side("LAC", False)
    home = _side("DEN", True)
    vegas = GamePreviewVegas(over_under=44.0)
    sections = build_game_narrative(LABEL, away, home, vegas)
    assert sections[0].entries == ["44 O/U"]


def test_vegas_section_omitted_when_over_under_missing():
    away = _side("LAC", False)
    home = _side("DEN", True)
    vegas = GamePreviewVegas(kickoff_label="Sun 4:25pm")
    sections = build_game_narrative(LABEL, away, home, vegas)
    assert len(sections) == 1
    assert sections[0].label is None
    assert sections[0].entries == [f"No notable Vegas, O vs D Line matchup, or player-tag signals yet for {LABEL}."]


def test_weather_is_never_included_in_sections():
    # Weather isn't a build_game_narrative input at all anymore -- it's
    # rendered separately by the frontend off GamePreviewGame.weather --
    # so there's nothing to pass here; this just documents that no section
    # ever mentions "Weather".
    away = _side("LAC", False)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    assert not any("Weather" in e for s in sections for e in s.entries)
    assert not any(s.label == "Weather" for s in sections)


def test_ol_dl_matchup_section_always_included_once_data_exists():
    # No notability gate anymore -- even numbers that would have been
    # "unremarkable" under the old DST-section thresholds still produce a
    # line, since this is inherently a two-sided comparison (see this
    # module's own _ol_dl_matchup_line docstring).
    matchup = GamePreviewDstMatchup(
        games=2,
        sacks_per_game_forced=1.5,
        takeaways_per_game_forced=0.5,
        opponent_sacks_per_game_allowed=1.0,
        opponent_takeaways_per_game_allowed=0.5,
    )
    away = _side("LAC", False, dst_matchup=matchup)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    section = _section(sections, "O vs D Line Matchup")
    assert any("LAC's D-line has forced 1.5 sacks" in e and "DEN's O-line has allowed 1.0 sacks" in e for e in section.entries)


def test_ol_dl_matchup_section_omitted_when_neither_side_has_data():
    away = _side("LAC", False)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    assert not any(s.label == "O vs D Line Matchup" for s in sections)


def test_ol_dl_matchup_section_includes_both_sides_even_when_one_alone_is_unremarkable():
    # Regression for the reported bug: an ARI @ SF game only showed ARI's
    # own line because SF's own forcing numbers alone didn't clear the old
    # notability bar -- both sides must always appear once either has data.
    matchup_away = GamePreviewDstMatchup(
        games=2, sacks_per_game_forced=4.0, takeaways_per_game_forced=2.0,
        opponent_sacks_per_game_allowed=1.0, opponent_takeaways_per_game_allowed=0.5,
    )
    matchup_home = GamePreviewDstMatchup(
        games=2, sacks_per_game_forced=0.5, takeaways_per_game_forced=0.0,
        opponent_sacks_per_game_allowed=0.0, opponent_takeaways_per_game_allowed=0.5,
    )
    away = _side("LAC", False, dst_matchup=matchup_away)
    home = _side("DEN", True, dst_matchup=matchup_home)
    sections = build_game_narrative(LABEL, away, home, None)
    section = _section(sections, "O vs D Line Matchup")
    assert len(section.entries) == 2
    assert any(e.startswith("LAC's D-line") for e in section.entries)
    assert any(e.startswith("DEN's D-line") for e in section.entries)


def test_pace_section_appears_with_no_bullets_when_one_side_has_pace_trend():
    # The Offensive Pace heading exists purely to gate the frontend's own
    # weeks-as-columns pace trend table -- it never carries prose bullets of
    # its own anymore (see _pace_section's docstring).
    pace = GamePreviewPaceTrend(
        week=10, plays=70, pass_att=45, rush_att=25, pass_rate_pct=64.3, rush_rate_pct=35.7,
    )
    away = _side("LAC", False, pace_trend=pace)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    pace_section = _section(sections, "Offensive Pace")
    assert pace_section.entries == []


def test_pace_section_omitted_when_no_pace_trend_at_all():
    away = _side("LAC", False)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    assert not any(s.label == "Offensive Pace" for s in sections)


def test_pace_section_appears_with_no_bullets_when_both_sides_have_pace_trend():
    away_pace = GamePreviewPaceTrend(
        week=10, plays=70, pass_att=45, rush_att=25, pass_rate_pct=64.3, rush_rate_pct=35.7,
        plays_delta=8, pass_rate_delta=12.0,
    )
    home_pace = GamePreviewPaceTrend(
        week=10, plays=55, pass_att=25, rush_att=30, pass_rate_pct=45.5, rush_rate_pct=54.5,
        plays_delta=-9, pass_rate_delta=-6.0,
    )
    away = _side("LAC", False, pace_trend=away_pace)
    home = _side("DEN", True, pace_trend=home_pace)
    sections = build_game_narrative(LABEL, away, home, None)
    pace_section = _section(sections, "Offensive Pace")
    assert pace_section.entries == []


def test_matchup_trends_section_included_when_exploitable_positions_present():
    exploitable = [
        GamePreviewPositionalMatchup(
            position="WR", games=3, avg_fpts_allowed=22.5, league_avg_fpts=15.0, high_multiplier_games=2
        )
    ]
    away = _side("LAC", False)
    home = _side("DEN", True, exploitable_positions=exploitable)
    sections = build_game_narrative(LABEL, away, home, None)
    matchup_section = _section(sections, "Matchup Trends")
    assert matchup_section.entries == [
        "DEN has allowed 22.5 FPTS/game to WRs (league avg 15.0) with 2 high-multiplier games over 3 games -- "
        "consider LAC's WRs."
    ]


def test_matchup_trends_section_omitted_when_no_exploitable_positions():
    away = _side("LAC", False)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    assert not any(s.label == "Matchup Trends" for s in sections)


def test_matchup_trends_section_combines_both_sides():
    away_exploitable = [
        GamePreviewPositionalMatchup(
            position="RB", games=3, avg_fpts_allowed=20.0, league_avg_fpts=14.0, high_multiplier_games=2
        )
    ]
    home_exploitable = [
        GamePreviewPositionalMatchup(
            position="TE", games=3, avg_fpts_allowed=18.0, league_avg_fpts=12.0, high_multiplier_games=2
        )
    ]
    away = _side("LAC", False, exploitable_positions=away_exploitable)
    home = _side("DEN", True, exploitable_positions=home_exploitable)
    sections = build_game_narrative(LABEL, away, home, None)
    matchup_section = _section(sections, "Matchup Trends")
    assert len(matchup_section.entries) == 2
    assert (
        "LAC has allowed 20.0 FPTS/game to RBs (league avg 14.0) with 2 high-multiplier games over 3 games -- "
        "consider DEN's RBs." in matchup_section.entries
    )
    assert (
        "DEN has allowed 18.0 FPTS/game to TEs (league avg 12.0) with 2 high-multiplier games over 3 games -- "
        "consider LAC's TEs." in matchup_section.entries
    )


def test_ownership_section_combines_both_sides_into_one_line():
    away = _side("LAC", False, projected_ownership_pct=30.0)
    home = _side("DEN", True, projected_ownership_pct=80.0)
    sections = build_game_narrative(LABEL, away, home, None, combined_projected_ownership_pct=110.0)
    section = _section(sections, "Ownership")
    assert any(e == "110.0% projected ownership = LAC 30.0% + DEN 80.0%" for e in section.entries)


def test_ownership_section_combined_line_no_icons_when_no_flags_given():
    # Flags default to None (a Phase-A/B/C-era caller/test that doesn't
    # compute ownership bands) -- no icon on any of the three numbers.
    away = _side("LAC", False, projected_ownership_pct=60.0)
    home = _side("DEN", True, projected_ownership_pct=55.0)
    sections = build_game_narrative(LABEL, away, home, None, combined_projected_ownership_pct=115.0)
    section = _section(sections, "Ownership")
    assert any(e == "115.0% projected ownership = LAC 60.0% + DEN 55.0%" for e in section.entries)


def test_ownership_section_combined_line_flags_low_owned_side():
    away = _side("LAC", False, projected_ownership_pct=30.0)
    home = _side("DEN", True, projected_ownership_pct=60.0)
    sections = build_game_narrative(
        LABEL, away, home, None,
        combined_projected_ownership_pct=90.0,
        away_ownership_flag="low",
    )
    section = _section(sections, "Ownership")
    assert any(e == "90.0% projected ownership = \U0001f4c9 LAC 30.0% + DEN 60.0%" for e in section.entries)


def test_ownership_section_combined_line_flags_high_owned_side():
    away = _side("LAC", False, projected_ownership_pct=30.0)
    home = _side("DEN", True, projected_ownership_pct=70.0)
    sections = build_game_narrative(
        LABEL, away, home, None,
        combined_projected_ownership_pct=100.0,
        home_ownership_flag="high",
    )
    section = _section(sections, "Ownership")
    assert any(e == "100.0% projected ownership = LAC 30.0% + \U0001f4c8 DEN 70.0%" for e in section.entries)


def test_ownership_section_combined_line_flags_the_game_total_too():
    away = _side("LAC", False, projected_ownership_pct=15.0)
    home = _side("DEN", True, projected_ownership_pct=20.0)
    sections = build_game_narrative(
        LABEL, away, home, None,
        combined_projected_ownership_pct=35.0,
        away_ownership_flag="low",
        home_ownership_flag="low",
        combined_ownership_flag="low",
    )
    section = _section(sections, "Ownership")
    assert any(
        e == "\U0001f4c9 35.0% projected ownership = \U0001f4c9 LAC 15.0% + \U0001f4c9 DEN 20.0%"
        for e in section.entries
    )


def test_ownership_section_omitted_when_no_ownership_data_at_all():
    away = _side("LAC", False)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    assert not any(s.label == "Ownership" for s in sections)


def test_ownership_section_includes_ratio_line():
    away = _side("LAC", False, projected_ownership_pct=60.0)
    home = _side("DEN", True, projected_ownership_pct=50.0)
    vegas = GamePreviewVegas(over_under=49.5)
    sections = build_game_narrative(
        LABEL, away, home, vegas,
        combined_projected_ownership_pct=110.0,
        total_to_ownership_ratio=2.22,
        high_over_under=False,
    )
    section = _section(sections, "Ownership")
    ratio_line = next(e for e in section.entries if e.startswith("Game Total-to-Ownership Ratio"))
    assert "2.22% ownership per O/U point on a 49.5 O/U" in ratio_line
    assert "high-total game" not in ratio_line
    assert "low-total game" not in ratio_line


def test_ownership_section_ratio_line_notes_high_over_under():
    away = _side("LAC", False, projected_ownership_pct=20.0)
    home = _side("DEN", True, projected_ownership_pct=15.0)
    vegas = GamePreviewVegas(over_under=51.5)
    sections = build_game_narrative(
        LABEL, away, home, vegas,
        combined_projected_ownership_pct=35.0,
        total_to_ownership_ratio=0.68,
        high_over_under=True,
    )
    section = _section(sections, "Ownership")
    ratio_line = next(e for e in section.entries if e.startswith("Game Total-to-Ownership Ratio"))
    assert "high-total game (O/U 47+)" in ratio_line


def test_ownership_section_ratio_line_notes_low_over_under():
    away = _side("LAC", False, projected_ownership_pct=20.0)
    home = _side("DEN", True, projected_ownership_pct=15.0)
    vegas = GamePreviewVegas(over_under=38.0)
    sections = build_game_narrative(
        LABEL, away, home, vegas,
        combined_projected_ownership_pct=35.0,
        total_to_ownership_ratio=0.92,
        high_over_under=False,
        low_over_under=True,
    )
    section = _section(sections, "Ownership")
    ratio_line = next(e for e in section.entries if e.startswith("Game Total-to-Ownership Ratio"))
    assert "low-total game (O/U 40 or under)" in ratio_line
    assert "high-total game" not in ratio_line


def test_vegas_section_leads_with_high_over_under_flag():
    # The High/Low O/U flag now leads the game's own Vegas bullet (the
    # first, label=None section, as a prefix on that single entry) instead
    # of leading the separate Ownership section or standing as its own
    # bullet -- is_high_over_under/is_low_over_under both require
    # over_under to be set, so a real vegas is needed here to see it.
    away = _side("LAC", False, projected_ownership_pct=20.0)
    home = _side("DEN", True, projected_ownership_pct=15.0)
    vegas = GamePreviewVegas(over_under=49.5)
    sections = build_game_narrative(LABEL, away, home, vegas, high_over_under=True)
    vegas_section = next(s for s in sections if s.label is None)
    assert vegas_section.entries == ["\U0001f525 High O/U 49.5 O/U"]
    ownership_section = _section(sections, "Ownership")
    assert "\U0001f525 High O/U" not in ownership_section.entries


def test_vegas_section_leads_with_low_over_under_flag():
    away = _side("LAC", False, projected_ownership_pct=20.0)
    home = _side("DEN", True, projected_ownership_pct=15.0)
    vegas = GamePreviewVegas(over_under=38.0)
    sections = build_game_narrative(LABEL, away, home, vegas, high_over_under=False, low_over_under=True)
    vegas_section = next(s for s in sections if s.label is None)
    assert vegas_section.entries == ["❄️ Low O/U 38 O/U"]
    ownership_section = _section(sections, "Ownership")
    assert "❄️ Low O/U" not in ownership_section.entries


def test_ownership_section_no_flag_line_when_neither_high_nor_low():
    away = _side("LAC", False, projected_ownership_pct=20.0)
    home = _side("DEN", True, projected_ownership_pct=15.0)
    sections = build_game_narrative(LABEL, away, home, None)
    section = _section(sections, "Ownership")
    assert "\U0001f525 High O/U" not in section.entries
    assert "❄️ Low O/U" not in section.entries


def test_ownership_section_ratio_line_omitted_without_vegas_but_combined_line_still_shows():
    # No vegas at all -- over_under can't be read off a None vegas, so the
    # ratio line can't be built even though combined/ratio were supplied.
    # The section still exists because the combined ownership line is
    # always shown regardless.
    away = _side("LAC", False, projected_ownership_pct=60.0)
    home = _side("DEN", True, projected_ownership_pct=50.0)
    sections = build_game_narrative(
        LABEL, away, home, None,
        combined_projected_ownership_pct=110.0,
        total_to_ownership_ratio=2.22,
        high_over_under=False,
    )
    section = _section(sections, "Ownership")
    assert not any(e.startswith("Game Total-to-Ownership Ratio") for e in section.entries)
    assert len(section.entries) == 1


def test_play_fade_monitor_each_get_own_labeled_section():
    away_players = [
        GamePreviewPlayer(name="Breakout WR", position="WR", team="LAC", tags=[GamePreviewPlayerTag(kind="play", reason="Breakout Watch")]),
        GamePreviewPlayer(name="Cooling RB", position="RB", team="LAC", tags=[GamePreviewPlayerTag(kind="fade", reason="Repeat Performer")]),
    ]
    home_players = [
        GamePreviewPlayer(name="Uncertain TE", position="TE", team="DEN", tags=[GamePreviewPlayerTag(kind="monitor", reason="Falling target share")]),
    ]
    away = _side("LAC", False, players=away_players)
    home = _side("DEN", True, players=home_players)
    sections = build_game_narrative(LABEL, away, home, None)

    play_section = _section(sections, "Plays to consider")
    assert play_section.entries == ["Breakout WR (Breakout Watch)"]

    fade_section = _section(sections, "Fade")
    assert fade_section.entries == ["Cooling RB (Repeat Performer)"]

    monitor_section = _section(sections, "Monitor")
    assert monitor_section.entries == ["Uncertain TE (Falling target share)"]


def test_leverage_and_chalk_tags_are_not_narrated():
    players = [
        GamePreviewPlayer(name="Deep Sleeper", position="WR", team="LAC", tags=[GamePreviewPlayerTag(kind="leverage", reason="Low ownership")]),
        GamePreviewPlayer(name="Popular Chalk", position="RB", team="LAC", tags=[GamePreviewPlayerTag(kind="chalk", reason="High ownership")]),
    ]
    away = _side("LAC", False, players=players)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    assert len(sections) == 1
    assert sections[0].label is None


def test_tag_section_is_uncapped():
    # No cap -- every player with a fired tag of this kind gets a line,
    # even a deep bench (a prior 3-name cap crowded out real signals purely
    # by alphabetical accident -- see this module's own docstring).
    players = [
        GamePreviewPlayer(name=f"Play {i}", position="WR", team="LAC", tags=[GamePreviewPlayerTag(kind="play", reason="Signal")])
        for i in range(5)
    ]
    away = _side("LAC", False, players=players)
    home = _side("DEN", True)
    sections = build_game_narrative(LABEL, away, home, None)
    play_section = _section(sections, "Plays to consider")
    assert len(play_section.entries) == 5


def test_full_narrative_section_order():
    matchup = GamePreviewDstMatchup(
        games=2,
        sacks_per_game_forced=4.0,
        takeaways_per_game_forced=2.0,
        opponent_sacks_per_game_allowed=1.0,
        opponent_takeaways_per_game_allowed=0.5,
    )
    vegas = GamePreviewVegas(over_under=45.5, away_implied_total=22.5, home_implied_total=23.0)
    players = [GamePreviewPlayer(name="Star WR", position="WR", team="LAC", tags=[GamePreviewPlayerTag(kind="play", reason="Rising share")])]
    away = _side("LAC", False, dst_matchup=matchup, players=players, projected_ownership_pct=20.0)
    home = _side("DEN", True)
    sections = build_game_narrative(
        LABEL, away, home, vegas,
        combined_projected_ownership_pct=20.0,
        total_to_ownership_ratio=0.44,
        high_over_under=False,
    )

    assert len(sections) == 4
    assert sections[0].label is None
    assert sections[0].entries == ["45.5 O/U (LAC 22.5 - DEN 23)"]
    assert sections[1].label == "Ownership"
    assert sections[2].label == "O vs D Line Matchup"
    assert sections[3].label == "Plays to consider"
