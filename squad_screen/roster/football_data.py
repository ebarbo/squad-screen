from __future__ import annotations

import logging
from urllib.parse import quote

from squad_screen.http import HttpClient
from squad_screen.models import Player, TeamRef
from squad_screen.names import fold, normalize_position, player_aliases

log = logging.getLogger(__name__)

COMPETITIONS = ("PL", "PD", "SA", "BL1", "FL1", "CL", "EL", "PPL", "DED")
BASE = "https://api.football-data.org/v4"


def _headers(api_key: str) -> dict[str, str]:
    return {"X-Auth-Token": api_key}


def _match(query: str, team: dict) -> bool:
    q = fold(query)
    names = [
        team.get("name") or "",
        team.get("shortName") or "",
        team.get("tla") or "",
    ]
    return any(q == fold(n) or q in fold(n) or fold(n) in q for n in names if n)


def _map_player(raw: dict) -> Player:
    name = (raw.get("name") or "").strip()
    position = raw.get("position")
    return Player(
        id=f"fd-{raw.get('id')}",
        name=name,
        position=position,
        position_code=normalize_position(position),
        nationality=raw.get("nationality"),
        date_of_birth=(raw.get("dateOfBirth") or "")[:10] or None,
        shirt_number=raw.get("shirtNumber"),
        source="football-data.org",
        aliases=player_aliases(name),
    )


async def fetch_football_data(
    client: HttpClient, query: str, api_key: str
) -> tuple[TeamRef | None, list[Player]]:
    if not api_key:
        return None, []
    headers = _headers(api_key)
    found: dict | None = None
    for code in COMPETITIONS:
        response = await client.get(f"{BASE}/competitions/{code}/teams", headers=headers)
        if response is None or response.status_code != 200:
            log.debug("football-data competition %s: %s", code, getattr(response, "status_code", None))
            continue
        for team in response.json().get("teams") or []:
            if _match(query, team):
                found = team
                break
        if found:
            break
    if not found:
        # Last chance: named search is not official, skip
        log.info("football-data.org: no team match for %s", query)
        return None, []

    detail = await client.get(f"{BASE}/teams/{found['id']}", headers=headers)
    if detail is None or detail.status_code != 200:
        return None, []
    data = detail.json()
    team = TeamRef(
        id=f"fd-{data.get('id')}",
        name=data.get("name") or query,
        short_name=data.get("shortName"),
        competition=None,
        venue=data.get("venue"),
        source="football-data.org",
        crest_url=data.get("crest"),
    )
    squad = [_map_player(p) for p in data.get("squad") or [] if p.get("name")]
    return team, squad


def search_url(query: str) -> str:
    return f"{BASE}/teams?name={quote(query)}"
