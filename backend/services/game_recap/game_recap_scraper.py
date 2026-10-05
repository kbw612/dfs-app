"""
Scrapes walterfootball.com's public "NFL Game Recaps" page for one
(season, week)'s per-game recap text -- the site's own written summary of
each game, captured and stored VERBATIM (see backend/schemas/game_recap/
game_recap.py's own docstring for why this app never summarizes it).

No login required -- confirmed live before building this scraper (unlike
Ownership's scrape of oneweekseason.com, see backend/services/ownership/
scraper.py).

URL shape: a past week lives at its own numbered URL,
https://walterfootball.com/nflreview{season}_{week:02d}.php (e.g.
nflreview2026_01.php) -- but the CURRENT week's recap only lives at the
bare, un-numbered https://walterfootball.com/nflreview.php until the
following week, when it gets promoted to its own numbered page and
nflreview.php moves on to the new current week. So scrape() always tries
the numbered URL first; on a 404 it falls back to the bare URL, but only
trusts that fallback if the fetched page's own <title> actually says
"Week {week}, {season}" -- otherwise the bare URL is showing some OTHER
week (e.g. you asked for a week that's neither archived yet nor current),
and this raises rather than silently saving the wrong week's recaps under
the requested week's filename.

Page structure (confirmed via a live browser read of the actual DOM, not
the earlier assumption -- see below): each game is its OWN container
<div> (one per game, no shared wrapper around the whole page's games),
holding two team-crest <img> tags, a <br>, the bold score line (e.g.
"Falcons 35, Packers 14" inside a <strong>/<b> tag), another <br>, and then
the recap itself as BARE TEXT NODES separated by <br> tags -- NOT wrapped
in <p> paragraphs the way an earlier version of this scraper assumed
(that assumption came from a markdown-rendered fetch of the page, which
silently reformats bare text+<br> into paragraph-looking output and hid
the real markup -- it produced an always-empty recap_text here, since
there were never any <p> siblings for the old code to find). The game's
own container ends with a boxscore thumbnail image ("nflbox" in its
filename) right after the last paragraph of text. Occasionally a bylined
recap (e.g. "By Charlie Campbell") adds bullets (an "EDITOR'S NOTE" aside
plus the body in list form) -- these are BARE <li> tags directly among the
score tag's own siblings, with no <ul>/<ol> wrapper at all (confirmed via
the same live browser read; _bullet_from_bare_li below handles this,
_bullets_from_list is kept only in case a future recap actually wraps its
list, which the page doesn't currently do).

_collect_recap_text walks the score tag's OWN siblings within its
container (BeautifulSoup .next_sibling, not find_all_next across the
whole document) so it can't bleed into a different game's container even
if a future markup change removes the per-game <div> wrapper -- a <br>
(or a block tag like <p>/<ul>/<ol>, in case the site changes back) flushes
the current run of text as its own paragraph; the boxscore image is a stop
signal (no text of its own); a "For more thoughts" transition is also kept
as a defensive stop in case this ever runs against an unwrapped page
layout again.

Team order in the score line is NOT reliable for home/away -- the site
wrote "Redskins 33, Seahawks 31" for a game Seattle played AT Washington
(home team listed first that time, confirmed against the Schedule file).
So scrape() resolves each game's real away_team/home_team from the
uploaded Schedule file (see backend/services/schedule/schedule_loader.py's
opponent_and_location, the same lookup Game Logs' own "vs"/"@" display
already uses) rather than trusting the page's own text order. A game the
Schedule file can't confirm (not uploaded, or either team's own name
didn't resolve to this app's abbreviation) falls back to the order
actually scraped, flagged in scrape()'s own `messages`.

Team names on this page are bare nicknames ("Falcons", "Packers"), not
this app's own abbreviations -- _TEAM_ALIASES below is built from
team_names.py's own abbrev->nickname table (reversed) plus a couple of
legacy/alternate spellings this site specifically uses (e.g. "Redskins"
for Washington, a running style quirk of the site's -- confirmed live,
not a guess). An unresolved name is NOT a reason to drop the game (same
convention as vegas_lines/scraper.py) -- the game is still returned with
the raw scraped name verbatim in that case.
"""

from __future__ import annotations

import re
from typing import Literal, NamedTuple

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from backend.config import settings
from backend.repositories.schedule.schedule_repo import load_schedule_csv
from backend.services.schedule.schedule_loader import ScheduleRow, opponent_and_location, parse_schedule_csv
from backend.services.shared.team_names import TEAM_NICKNAME_BY_ABBREV

_TEAM_ALIASES: dict[str, str] = {nickname.lower(): abbrev for abbrev, nickname in TEAM_NICKNAME_BY_ABBREV.items()}
# Legacy/alternate spellings specific to this site, confirmed via a live
# fetch -- walterfootball still uses "Redskins" for Washington as a
# running style choice rather than the team's current name.
_TEAM_ALIASES.update(
    {
        "redskins": "WAS",
        "football team": "WAS",
    }
)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# "Falcons 35, Packers 14" -- team names are letters/digits/periods/
# apostrophes/spaces. Digits are required in the name charset for "49ers"
# (San Francisco) -- without them, this regex simply never matched that
# team's own score line at all (non-greedy quantifiers still stop at the
# earliest point that lets the rest of the pattern match, so adding digits
# to the name charset doesn't risk the score digits getting swallowed into
# the name group), which silently dropped the ENTIRE game from parse_games'
# output, not just its score -- confirmed live: a 49ers game was missing
# wholesale from a scrape until this was added.
_SCORE_LINE_RE = re.compile(r"^([A-Za-z0-9.' ]+?)\s+(\d+),\s*([A-Za-z0-9.' ]+?)\s+(\d+)$")

# Recap blocks stop collecting once they hit this transition (the page's
# own move into unrelated links after the LAST game) -- kept as a
# defensive fallback (see this module's own docstring); the current
# per-game <div> wrapper already makes this unreachable in practice.
_CLOSING_TRANSITION = "For more thoughts"


def resolve_team_abbrev(name: str) -> str | None:
    return _TEAM_ALIASES.get(name.strip().lower())


def fetch_html(url: str) -> requests.Response:
    """Returns the raw response (not just `.text`) so callers can branch
    on status_code (scrape()'s numbered-URL-then-bare-URL fallback) without
    a second round trip."""
    return requests.get(url, headers=_BROWSER_HEADERS, timeout=settings.request_timeout_seconds)


def _page_matches_week(html: str, season: int, week: int) -> bool:
    """True if this page's own <title> says it's for exactly this
    (season, week) -- e.g. "NFL Game Recaps: Week 3, 2026 - WalterFootball".
    Only used to validate the bare-URL fallback (see this module's own
    docstring) -- a numbered URL's week is already unambiguous from the URL
    itself, so scrape() doesn't bother calling this for that path."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    return re.search(rf"Week\s+{week}\s*,\s*{season}\b", title) is not None


def _is_score_tag(tag: Tag) -> re.Match | None:
    if tag.name not in ("strong", "b"):
        return None
    text = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
    return _SCORE_LINE_RE.match(text)


def _is_boxscore_image(tag: Tag) -> bool:
    if tag.name != "img":
        return False
    src = tag.get("src") or ""
    return "nflbox" in src.lower()


def _bullets_from_list(tag: Tag) -> str:
    items = [li.get_text(" ", strip=True) for li in tag.find_all("li", recursive=False)]
    return "\n".join(f"- {item}" for item in items if item)


def _bullet_from_bare_li(tag: Tag) -> str:
    """A Charlie Campbell-bylined recap's own bullets aren't wrapped in a
    <ul> at all on the real page (confirmed via a live browser read, not
    an earlier guess) -- bare <li> tags sit directly among the score tag's
    own siblings, same level as the surrounding <br>s. Each one becomes
    its own "- " paragraph, same rendering as a properly-wrapped list."""
    text = tag.get_text(" ", strip=True)
    return f"- {text}" if text else ""


def _collect_recap_text(score_tag: Tag) -> str:
    """Walks score_tag's own siblings (within its container -- see this
    module's own docstring) collecting the recap's bare text, using each
    <br> (or a block tag, in case the site ever reverts to <p>-wrapped
    recaps) as a paragraph boundary. Stops at the game's boxscore
    thumbnail, the next game's own score line (only reachable if a future
    markup change removes the per-game container), or the page's closing
    "For more thoughts" transition."""
    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        joined = re.sub(r"\s+", " ", "".join(buffer)).strip()
        if joined:
            paragraphs.append(joined)
        buffer.clear()

    for sibling in score_tag.next_siblings:
        if isinstance(sibling, NavigableString):
            text = str(sibling)
            if _CLOSING_TRANSITION in text:
                break
            buffer.append(text)
            continue

        if not isinstance(sibling, Tag):
            continue

        if sibling.name == "br":
            flush()
            continue

        if _is_boxscore_image(sibling):
            break

        if sibling.name in ("strong", "b") and _is_score_tag(sibling):
            break  # next game's own score line -- only reachable without a per-game container

        block_text = re.sub(r"\s+", " ", sibling.get_text(" ", strip=True)).strip()
        if _CLOSING_TRANSITION in block_text:
            break

        if sibling.name in ("ul", "ol"):
            flush()
            bullets = _bullets_from_list(sibling)
            if bullets:
                paragraphs.append(bullets)
            continue

        if sibling.name == "li":
            flush()
            bullet = _bullet_from_bare_li(sibling)
            if bullet:
                paragraphs.append(bullet)
            continue

        if sibling.name in ("p", "div"):
            flush()
            if block_text:
                paragraphs.append(block_text)
            continue

        # Inline tag (e.g. <a>, <em>) -- its text belongs in the current
        # running paragraph, same as a plain text node.
        buffer.append(sibling.get_text(" ", strip=True))

    flush()
    return "\n\n".join(paragraphs)


class ScrapedGame(NamedTuple):
    """One game's own text as parsed off the page, BEFORE the real
    away/home order is resolved from the Schedule file (see scrape()) --
    team_x/team_y are named generically rather than away/home because the
    order they're scraped in is just whatever order the site's own score
    line happened to list them, which this module's own docstring explains
    is not reliable for home/away."""

    team_x_name: str
    team_x_score: int
    team_y_name: str
    team_y_score: int
    recap_text: str

    @property
    def team_x(self) -> str:
        return resolve_team_abbrev(self.team_x_name) or self.team_x_name

    @property
    def team_y(self) -> str:
        return resolve_team_abbrev(self.team_y_name) or self.team_y_name


class ResolvedGameRecap(NamedTuple):
    """One game, in its final away_team/home_team order -- what scrape()
    actually returns, ready for the API layer to persist 1:1 as a
    GameRecapEntry (see backend/api/game_recap/scrape.py)."""

    away_team: str
    home_team: str
    away_team_score: int
    home_team_score: int
    recap_text: str


def parse_games(html: str) -> tuple[list[ScrapedGame], list[str]]:
    """Every game block this page's HTML parses cleanly into a
    ScrapedGame, plus human-readable messages for anything odd (no score
    lines found at all, or an unrecognized team name -- the latter isn't a
    skip reason, same convention as vegas_lines/scraper.py). Doesn't
    resolve away/home order -- that needs the Schedule file, which this
    function has no access to (see scrape(), which does both steps)."""
    soup = BeautifulSoup(html, "html.parser")
    score_tags = [tag for tag in soup.find_all(["strong", "b"]) if _is_score_tag(tag)]

    games: list[ScrapedGame] = []
    messages: list[str] = []
    if not score_tags:
        messages.append("No game score lines found on the page -- page structure may have changed")

    for tag in score_tags:
        match = _is_score_tag(tag)
        assert match is not None  # score_tags was already filtered on this
        team_x_name, x_score, team_y_name, y_score = match.groups()
        team_x_name, team_y_name = team_x_name.strip(), team_y_name.strip()

        if resolve_team_abbrev(team_x_name) is None:
            messages.append(f"Unrecognized team name {team_x_name!r} -- shown verbatim")
        if resolve_team_abbrev(team_y_name) is None:
            messages.append(f"Unrecognized team name {team_y_name!r} -- shown verbatim")

        recap_text = _collect_recap_text(tag)
        if not recap_text:
            messages.append(f"No recap text found for {team_x_name} {x_score}, {team_y_name} {y_score}")

        games.append(
            ScrapedGame(
                team_x_name=team_x_name,
                team_x_score=int(x_score),
                team_y_name=team_y_name,
                team_y_score=int(y_score),
                recap_text=recap_text,
            )
        )

    return games, messages


def resolve_away_home(
    team_x: str, team_y: str, schedule_rows: list[ScheduleRow], week: int
) -> tuple[str, str, bool]:
    """(away_team, home_team, resolved) for two already-abbreviated teams,
    using the Schedule file's own opponent_and_location lookup -- NOT the
    site's score-line text order (see this module's own docstring for why
    that's unreliable). Checks both teams' own schedule rows (either one
    confirming the other as its opponent, with a Home/Away GameLocation,
    is enough) since the Schedule file's row-per-team layout means either
    side could be the one carrying the usable row. Falls back to
    (team_x, team_y) -- the order actually scraped -- with resolved=False
    when neither side's row confirms the matchup (Schedule not uploaded,
    or either team name never resolved to this app's abbreviation, so it
    can't match a schedule row at all)."""
    for team_a, team_b in ((team_x, team_y), (team_y, team_x)):
        result = opponent_and_location(schedule_rows, team_a, week)
        if result is not None and result[0] == team_b and result[1] in ("Home", "Away"):
            return (team_a, team_b, True) if result[1] == "Away" else (team_b, team_a, True)
    return team_x, team_y, False


def build_recap_url(season: int, week: int) -> str:
    return settings.walterfootball_recap_week_url_template.format(season=season, week=week)


def _load_schedule_rows(season: int) -> list[ScheduleRow]:
    csv_text = load_schedule_csv(settings.nfl_data_dir, season)
    return parse_schedule_csv(csv_text) if csv_text is not None else []


UrlMode = Literal["auto", "week_page", "current_page"]


def _fetch_week_page(season: int, week: int) -> tuple[str, str]:
    """Fetches ONLY the numbered per-week URL, no fallback. Raises
    RuntimeError on anything but a 200 -- used when the person explicitly
    picked "Week page" in Settings (see this module's own docstring for
    why a past week isn't always there yet: it only exists once that week
    has been archived)."""
    numbered_url = build_recap_url(season, week)
    response = fetch_html(numbered_url)
    if response.status_code != 200:
        raise RuntimeError(
            f"{numbered_url} isn't available (status {response.status_code}) -- season {season} week {week} "
            "may not be archived yet. Try \"Current week page\" instead if this is the latest week."
        )
    return response.text, numbered_url


def _fetch_current_page(season: int, week: int) -> tuple[str, str]:
    """Fetches ONLY the bare, un-numbered current-week URL, no fallback.
    Still validates the page's own <title> against the requested
    (season, week) -- even picking this mode explicitly shouldn't silently
    save one week's recaps under a different week's filename if the site's
    "current" page has already moved on. Raises RuntimeError on a fetch
    failure or a title mismatch."""
    current_url = settings.walterfootball_recap_current_url
    response = fetch_html(current_url)
    if response.status_code != 200:
        raise RuntimeError(f"{current_url} didn't load (status {response.status_code}).")
    if not _page_matches_week(response.text, season, week):
        raise RuntimeError(
            f"{current_url} is showing a different week than season {season} week {week} right now -- "
            'nothing to scrape. Try "Week page" instead if this week has already been archived there.'
        )
    return response.text, current_url


def scrape(season: int, week: int, url_mode: UrlMode = "auto") -> tuple[list[ResolvedGameRecap], list[str], str]:
    """Orchestrates fetch -> parse -> away/home resolution for this
    (season, week). `url_mode` picks which of walterfootball's two URL
    shapes to fetch from (see this module's own docstring for why there
    are two at all):
    - "week_page": only the numbered per-week URL (nflreview{season}_
      {week:02d}.php) -- the archived page for a week that's already past.
    - "current_page": only the bare, un-numbered URL (nflreview.php) --
      wherever the site currently has its "latest week" page pointed, which
      becomes the requested week's content only once that's actually true.
    - "auto" (default, used when the Settings panel's own toggle hasn't
      been exercised, and by every existing caller/test): try "week_page"
      first, fall back to "current_page" on a 404 -- the original
      numbered-then-bare fallback this function always had, before the
      Settings panel gave the person explicit control over which one to
      use (e.g. forcing "current_page" for the latest week before it's
      been archived, if "week_page" would otherwise 404 there anyway, or
      forcing "week_page" to avoid a "current_page" title mismatch).
    Returns (games, messages, source_url_actually_used). Callers are
    responsible for persisting the result (see backend/api/game_recap/
    scrape.py) -- this function has no side effects of its own (loading
    the Schedule file is a read, not a write).

    Raises RuntimeError if the selected mode's own fetch fails (see
    _fetch_week_page/_fetch_current_page), or in "auto" mode, if BOTH
    URLs fail."""
    if url_mode == "week_page":
        html, source_url = _fetch_week_page(season, week)
    elif url_mode == "current_page":
        html, source_url = _fetch_current_page(season, week)
    else:
        numbered_url = build_recap_url(season, week)
        response = fetch_html(numbered_url)
        if response.status_code == 200:
            html, source_url = response.text, numbered_url
        else:
            current_url = settings.walterfootball_recap_current_url
            current_response = fetch_html(current_url)
            if current_response.status_code != 200:
                raise RuntimeError(
                    f"Couldn't fetch a recap for season {season} week {week} -- "
                    f"neither {numbered_url} nor the current-week page ({current_url}) loaded."
                )
            if not _page_matches_week(current_response.text, season, week):
                raise RuntimeError(
                    f"Season {season} week {week} isn't archived yet at {numbered_url}, and the "
                    f"current-week page ({current_url}) is for a different week -- nothing to scrape."
                )
            html, source_url = current_response.text, current_url

    scraped_games, messages = parse_games(html)

    schedule_rows = _load_schedule_rows(season)
    resolved_games: list[ResolvedGameRecap] = []
    for game in scraped_games:
        away_team, home_team, resolved = resolve_away_home(game.team_x, game.team_y, schedule_rows, week)
        if not resolved:
            messages.append(
                f"Couldn't confirm home/away for {away_team} vs {home_team} from the Schedule file -- "
                "showing in the order scraped"
            )
        away_score = game.team_x_score if away_team == game.team_x else game.team_y_score
        home_score = game.team_y_score if home_team == game.team_y else game.team_x_score
        resolved_games.append(
            ResolvedGameRecap(
                away_team=away_team,
                home_team=home_team,
                away_team_score=away_score,
                home_team_score=home_score,
                recap_text=game.recap_text,
            )
        )

    return resolved_games, messages, source_url
