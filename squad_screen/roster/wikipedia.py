from __future__ import annotations

import logging
import re
from datetime import date

from bs4 import BeautifulSoup, Tag

from squad_screen.http import HttpClient
from squad_screen.models import Player, TeamRef
from squad_screen.names import normalize_position, player_aliases
from squad_screen.teams import canonical_team_name

log = logging.getLogger(__name__)

API = "https://en.wikipedia.org/w/api.php"

SKIP_HEADINGS = (
    "reserve",
    "youth",
    "academy",
    "out on loan",
    "loan",
    "staff",
    "coaching",
    "manager",
    "result",
    "fixture",
    "match",
    "record",
    "statistic",
    "award",
    "appearance",
    "goalscorer",
    "kit",
)

BLOCKED_NAMES = {
    "transfer from",
    "transfer to",
    "summer",
    "winter",
    "nat.",
    "nat",
    "apps",
    "goals",
    "goalkeepers",
    "defenders",
    "midfielders",
    "forwards",
    "player",
    "total",
    "own goals",
    "notes",
}

MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)


def _current_season_label(today: date | None = None) -> str:
    today = today or date.today()
    start = today.year if today.month >= 7 else today.year - 1
    end = (start + 1) % 100
    return f"{start}–{end:02d}"


def _season_titles(team: str) -> list[str]:
    season = _current_season_label()
    canonical = canonical_team_name(team)
    return [
        f"{season} {canonical} season",
        f"{canonical} current season",
        canonical,
    ]


def _heading_for(table: Tag) -> str:
    caption = table.find("caption")
    if caption:
        text = caption.get_text(" ", strip=True)
        if text:
            return text
    node: Tag | None = table
    while node is not None and node.parent and node.parent.name in {"td", "tr", "tbody", "thead", "table"}:
        node = node.parent
    current = node
    while current is not None:
        prev = current.find_previous(["h2", "h3", "h4"])
        if prev:
            return prev.get_text(" ", strip=True)
        current = current.parent
    return ""


def _skip_section(heading: str) -> bool:
    key = heading.lower()
    return any(token in key for token in SKIP_HEADINGS) and "squad" not in key


def _is_squad_table(table: Tag) -> bool:
    headers = [th.get_text(" ", strip=True).lower() for th in table.select("tr th")]
    blob = " ".join(headers)
    if "player" not in blob:
        return False
    markers = sum(
        1
        for token in ("pos", "position", "no.", "no", "nation", "nat", "squad")
        if any(token == h or token in h.split() for h in headers) or token in blob
    )
    return markers >= 2


def _cell_texts(row: Tag) -> list[str]:
    return [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]


def _parse_row(texts: list[str]) -> Player | None:
    number: int | None = None
    position: str | None = None
    name: str | None = None
    for text in texts:
        compact = text.strip()
        if not compact:
            continue
        if re.fullmatch(r"(GK|DF|MF|FW|CB|LB|RB|DM|CM|AM|LW|RW|ST|WB)", compact, re.I):
            position = compact
            continue
        if compact.lower() in {"player", "nation", "notes", "pos.", "pos", "no.", "no"}:
            continue
        if re.fullmatch(r"[A-Z]{2,3}", compact):
            continue
        if number is None and re.fullmatch(r"\d{1,2}", compact):
            number = int(compact)
            continue
        if name is None and re.search(r"[A-Za-zÀ-ÿ]{3,}", compact):
            cleaned = re.sub(r"\[.*?\]", "", compact)
            cleaned = re.sub(r"\(.*?\)", "", cleaned).strip(" ,")
            if len(cleaned) >= 3:
                name = cleaned
    if not name:
        return None
    if name.lower() in BLOCKED_NAMES:
        return None
    joined = " ".join(texts)
    if re.search(r"\buntil\b|\bat [A-Z]", joined) and re.search(r"loan|until", joined, re.I):
        return None
    if re.search(rf"\d{{1,2}}\s+({'|'.join(MONTHS)})\s+\d{{4}}", name, re.I):
        return None
    if re.fullmatch(r"[\d\s./\-]+", name):
        return None
    if len(name) > 40:
        return None
    return Player(
        id=f"wiki-{name.lower().replace(' ', '-')}",
        name=name,
        position=position,
        position_code=normalize_position(position),
        shirt_number=number,
        source="wikipedia",
        aliases=player_aliases(name),
    )


def parse_squad_tables(html: str, source_page: str) -> list[Player]:
    soup = BeautifulSoup(html, "lxml")
    players: list[Player] = []
    seen: set[str] = set()
    for table in soup.select("table.wikitable, table.sortable"):
        if not _is_squad_table(table):
            continue
        heading = _heading_for(table)
        if _skip_section(heading):
            continue
        for row in table.select("tr"):
            player = _parse_row(_cell_texts(row))
            if not player:
                continue
            key = player.name.lower()
            if key in seen:
                continue
            seen.add(key)
            player.source = f"wikipedia:{source_page}"
            players.append(player)
    return players


async def _fetch_html(client: HttpClient, title: str) -> str | None:
    response = await client.get(
        API,
        params={
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "redirects": 1,
        },
    )
    if response is None or response.status_code != 200:
        return None
    payload = response.json()
    if payload.get("error"):
        return None
    html = (payload.get("parse") or {}).get("text", {}).get("*")
    return html


async def fetch_wikipedia(
    client: HttpClient, query: str
) -> tuple[TeamRef | None, list[Player]]:
    titles = _season_titles(query)
    search = await client.get(
        API,
        params={
            "action": "opensearch",
            "search": canonical_team_name(query),
            "limit": 5,
            "namespace": 0,
            "format": "json",
        },
    )
    if search is not None and search.status_code == 200:
        data = search.json()
        if isinstance(data, list) and len(data) > 1:
            # Prefer season pages, then the club page.
            extra = list(data[1])
            titles = extra + titles

    ordered: list[str] = []
    for title in titles:
        if title not in ordered:
            ordered.append(title)
    ordered.sort(
        key=lambda t: (
            0 if t.lower() == canonical_team_name(query).lower() else 1,
            0 if "season" not in t.lower() else 2,
            t,
        )
    )

    seen_titles: set[str] = set()
    best: tuple[TeamRef, list[Player]] | None = None
    for title in ordered:
        if title in seen_titles:
            continue
        seen_titles.add(title)
        html = await _fetch_html(client, title)
        if not html:
            continue
        players = parse_squad_tables(html, title)
        if len(players) >= 11:
            log.info("Wikipedia squad from %s (%s players)", title, len(players))
            team = TeamRef(
                id=f"wiki-{title}",
                name=canonical_team_name(query),
                source=f"wikipedia:{title}",
            )
            if len(players) >= 18:
                return team, players
            if best is None or len(players) > len(best[1]):
                best = (team, players)
    if best:
        return best
    return None, []
