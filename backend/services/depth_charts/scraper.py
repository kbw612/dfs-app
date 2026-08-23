"""
Step 1 of the pipeline (Section 2 of the design doc): scrape() and
build_json(). Fetches footballguys.com's all-teams depth chart page and
parses it directly into the lean snapshot shape -- no intermediate
wide/list-cell CSV, no Python-list-literal-in-a-cell parsing anywhere.

Ported and cleaned up from get_depth_charts_no_business_rules_v2.py, with
the bug noted in the design doc fixed (the stray indentation around the
team-info.csv load in the original notebook cell).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup, Tag

from backend.config import settings
from backend.schemas.depth_charts.snapshot import Message, Player, Snapshot, Team

# Order positions are presented in when scraped; anything encountered that
# isn't in this list gets appended (sorted) after these.
DESIRED_POSITION_ORDER = [
    "QB", "RB", "WR", "TE", "FB", "LT", "LG", "C", "RG", "RT",
    "LDE", "RDE", "NT", "LDT", "RDT", "WLB", "SLB", "MLB", "LILB", "RILB",
    "LCB", "RCB", "SCB", "FS", "SS", "PK", "KR", "PR", "P", "H", "LS",
]

# footballguys.com's depth-chart page includes a coaching-staff section
# alongside actual player positions (visible as the "Coachess" column in the
# original script's wide CSV output -- position label "Coaches" + the
# script's own "s"-appending convention). Coaches aren't players and don't
# belong in `positions`, so any label matching these (case-insensitively)
# gets dropped before building the position list. Add more variants here if
# the live site turns out to use a different label.
EXCLUDED_POSITIONS = {"COACHES", "COACH", "COACHING STAFF"}

_INJURY_STATUS_RE = re.compile(r"\((\w+)\)\s*$")


def extract_injury_status(raw_name: str) -> tuple[str, str | None]:
    """'James Conner (Q)' -> ('James Conner', 'Q'). No match -> (name, None)."""
    match = _INJURY_STATUS_RE.search(raw_name)
    if not match:
        return raw_name.strip(), None
    status = match.group(1)
    clean_name = _INJURY_STATUS_RE.sub("", raw_name).strip()
    return clean_name, status


def _get_tag_text(tag: Tag, tag_name: str, class_name: str) -> str | None:
    found = tag.find(tag_name, class_=class_name)
    return found.get_text(strip=True) if found else None


def _get_unique_positions(depth_chart_tags: list[Tag]) -> set[str]:
    positions: set[str] = set()
    for depth_chart in depth_chart_tags:
        for pos_label in depth_chart.find_all("span", class_="pos-label"):
            cleaned = pos_label.get_text(strip=True).replace(":", "").strip()
            if cleaned:
                positions.add(cleaned)
    return positions


def _get_position_players(depth_chart_tag: Tag, position: str) -> list[Player]:
    li = depth_chart_tag.find("li", class_=f"depth-chart-pos-{position.lower()}")
    if li is None:
        return []

    players: list[Player] = []
    for player_tag in li.find_all(["a", "span"], class_="player"):
        raw_name = player_tag.get_text(strip=True)
        if not raw_name:
            continue
        clean_name, status = extract_injury_status(raw_name)
        players.append(Player(player=clean_name, status=status))
    return players


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    return response.text


def parse_teams(html: str) -> tuple[list[Team], list[Message]]:
    """Parse the scraped HTML into Team objects (team_abbrev/defensive_formation
    left unset here -- those are separate enrichment steps) plus any
    scrape-level messages worth surfacing.
    """
    soup = BeautifulSoup(html, "html.parser")
    depth_chart_tags = soup.find_all("div", class_="depth-chart")

    messages: list[Message] = []
    if len(depth_chart_tags) != 32:
        messages.append(
            Message(
                level="warning",
                step="scrape",
                message=(
                    f"Expected 32 teams, found {len(depth_chart_tags)} "
                    "-- page structure may have changed"
                ),
            )
        )

    observed_positions = {
        p for p in _get_unique_positions(depth_chart_tags)
        if p.upper() not in EXCLUDED_POSITIONS
    }
    positions_in_order = [p for p in DESIRED_POSITION_ORDER if p in observed_positions]
    positions_not_in_order = sorted(observed_positions - set(DESIRED_POSITION_ORDER))
    all_positions = positions_in_order + positions_not_in_order

    teams: list[Team] = []
    for depth_chart_tag in depth_chart_tags:
        team_name = _get_tag_text(depth_chart_tag, "span", "team-header")
        if not team_name:
            messages.append(
                Message(
                    level="error",
                    step="scrape",
                    message="Found a depth-chart block with no team-header -- skipped",
                )
            )
            continue

        positions = {
            position: _get_position_players(depth_chart_tag, position)
            for position in all_positions
        }
        teams.append(Team(team_name=team_name, positions=positions))

    return teams, messages


def build_json(teams: list[Team], messages: list[Message], source_url: str) -> Snapshot:
    return Snapshot(
        scraped_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        source_url=source_url,
        messages=list(messages),
        teams=teams,
    )


def scrape() -> Snapshot:
    """Orchestrates fetch -> parse -> build for this step of the pipeline.
    team_abbrev and defensive_formation are NOT set here -- see
    app.services.depth_charts.enrich, which runs next.
    """
    html = fetch_html(settings.source_url)
    teams, messages = parse_teams(html)
    return build_json(teams, messages, settings.source_url)
