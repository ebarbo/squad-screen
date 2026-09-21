from __future__ import annotations

import logging
import re

from squad_screen.http import HttpClient
from squad_screen.models import Player, TeamRef
from squad_screen.names import fold, normalize_position, player_aliases
from squad_screen.teams import canonical_team_name

log = logging.getLogger(__name__)

SEARCH = "https://www.thesportsdb.com/api/v1/json/{key}/searchteams.php"
PLAYERS = "https://www.thesportsdb.com/api/v1/json/{key}/lookup_all_players.php"


def _score_team(query: str, candidate: dict) -> int:
    name = fold(candidate.get("strTeam") or "")
    q = fold(query)
    score = 0
    if name == q:
        score += 10
    if q in name:
        score += 4
    if (candidate.get("strSport") or "").lower() == "soccer":
        score += 6
    league = fold(candidate.get("strLeague") or "")
    for needle in ("premier", "la liga", "serie a", "bundesliga", "ligue 1", "champions"):
        if needle in league:
            score += 3
    return score


def _map_player(raw: dict, source: str) -> Player:
    name = (raw.get("strPlayer") or "").strip()
    pid = str(raw.get("idPlayer") or name)
    position = raw.get("strPosition") or raw.get("strPosition2")
    number = raw.get("strNumber")
    shirt: int | None = None
    if number and str(number).isdigit():
        shirt = int(number)
    return Player(
        id=pid,
        name=name,
        position=position,
        position_code=normalize_position(position),
        nationality=raw.get("strNationality"),
        date_of_birth=raw.get("dateBorn"),
        shirt_number=shirt,
        source=source,
        aliases=player_aliases(name),
    )


async def fetch_sportsdb(
    client: HttpClient, query: str, api_key: str
) -> tuple[TeamRef | None, list[Player]]:
    key = api_key or "123"
    searches = []
    for candidate in (query, canonical_team_name(query), re.sub(r"\b(fc|cf|afc|sc|club)\b", "", query, flags=re.I).strip()):
        if candidate and candidate not in searches:
            searches.append(candidate)

    best_team: dict | None = None
    best_score = -1
    for term in searches:
        response = await client.get(SEARCH.format(key=key), params={"t": term})
        if response is None or response.status_code != 200:
            continue
        teams = response.json().get("teams") or []
        soccer = [t for t in teams if fold(t.get("strSport") or "") in {"soccer", "football"}]
        for team in soccer:
            score = _score_team(query, team)
            if score > best_score:
                best_score = score
                best_team = team
        if best_team and best_score >= 10:
            break
    if not best_team:
        log.info("TheSportsDB: no soccer team for %s", query)
        return None, []
    team = TeamRef(
        id=str(best_team.get("idTeam")),
        name=best_team.get("strTeam") or query,
        short_name=best_team.get("strTeamShort"),
        competition=best_team.get("strLeague"),
        venue=best_team.get("strStadium"),
        source="thesportsdb",
        crest_url=best_team.get("strBadge") or best_team.get("strLogo"),
    )
    players_resp = await client.get(PLAYERS.format(key=key), params={"id": team.id})
    if players_resp is None or players_resp.status_code != 200:
        return team, []
    rows = (players_resp.json() or {}).get("player") or []
    players = [_map_player(row, "thesportsdb") for row in rows if row.get("strPlayer")]
    return team, players
