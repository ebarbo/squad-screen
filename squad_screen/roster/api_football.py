from __future__ import annotations

import logging

from squad_screen.http import HttpClient
from squad_screen.models import Player, TeamRef
from squad_screen.names import fold, normalize_position, player_aliases

log = logging.getLogger(__name__)

BASE = "https://v3.football.api-sports.io"


def _headers(api_key: str) -> dict[str, str]:
    return {"x-apisports-key": api_key}


def _match(query: str, team: dict) -> bool:
    q = fold(query)
    names = [team.get("name") or "", team.get("code") or ""]
    return any(q == fold(n) or q in fold(n) for n in names if n)


def _map_player(raw: dict) -> Player:
    name = (raw.get("name") or "").strip()
    position = raw.get("position")
    return Player(
        id=f"af-{raw.get('id')}",
        name=name,
        position=position,
        position_code=normalize_position(position),
        nationality=None,
        date_of_birth=None,
        shirt_number=raw.get("number"),
        source="api-football",
        aliases=player_aliases(name),
    )


async def fetch_api_football(
    client: HttpClient, query: str, api_key: str
) -> tuple[TeamRef | None, list[Player]]:
    if not api_key:
        return None, []
    headers = _headers(api_key)
    response = await client.get(f"{BASE}/teams", headers=headers, params={"name": query})
    if response is None or response.status_code != 200:
        log.warning("API-Football team search failed: %s", getattr(response, "status_code", None))
        return None, []
    rows = response.json().get("response") or []
    match = None
    for row in rows:
        team = row.get("team") or {}
        if _match(query, team):
            match = row
            break
    if not match and rows:
        match = rows[0]
    if not match:
        return None, []
    team_info = match.get("team") or {}
    venue = (match.get("venue") or {}).get("name")
    team = TeamRef(
        id=f"af-{team_info.get('id')}",
        name=team_info.get("name") or query,
        short_name=team_info.get("code"),
        venue=venue,
        source="api-football",
        crest_url=team_info.get("logo"),
    )
    squad_resp = await client.get(
        f"{BASE}/players/squads",
        headers=headers,
        params={"team": team_info.get("id")},
    )
    if squad_resp is None or squad_resp.status_code != 200:
        return team, []
    payload = squad_resp.json().get("response") or []
    players_raw = []
    if payload:
        players_raw = payload[0].get("players") or []
    players = [_map_player(p) for p in players_raw if p.get("name")]
    return team, players
