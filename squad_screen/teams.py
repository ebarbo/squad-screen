from __future__ import annotations

TEAM_ALIASES: dict[str, str] = {
    "barcelona": "FC Barcelona",
    "barca": "FC Barcelona",
    "barça": "FC Barcelona",
    "fcb": "FC Barcelona",
    "real madrid": "Real Madrid",
    "madrid": "Real Madrid",
    "atletico": "Atlético Madrid",
    "atlético": "Atlético Madrid",
    "man city": "Manchester City",
    "manchester city": "Manchester City",
    "city": "Manchester City",
    "man united": "Manchester United",
    "manchester united": "Manchester United",
    "united": "Manchester United",
    "liverpool": "Liverpool",
    "arsenal": "Arsenal",
    "chelsea": "Chelsea",
    "tottenham": "Tottenham Hotspur",
    "spurs": "Tottenham Hotspur",
    "bayern": "FC Bayern München",
    "bayern munich": "FC Bayern München",
    "dortmund": "Borussia Dortmund",
    "bvb": "Borussia Dortmund",
    "psg": "Paris Saint-Germain",
    "paris": "Paris Saint-Germain",
    "juventus": "Juventus",
    "inter": "Inter Milan",
    "ac milan": "AC Milan",
    "milan": "AC Milan",
    "napoli": "SSC Napoli",
    "roma": "AS Roma",
    "atletico madrid": "Atlético Madrid",
    "athletic": "Athletic Club",
    "leverkusen": "Bayer 04 Leverkusen",
    "leipzig": "RB Leipzig",
    "psv": "PSV Eindhoven",
    "psv eindhoven": "PSV Eindhoven",
}


def canonical_team_name(query: str) -> str:
    key = query.strip().lower()
    return TEAM_ALIASES.get(key, query.strip())
