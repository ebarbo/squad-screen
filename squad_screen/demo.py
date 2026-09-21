from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from squad_screen.models import Article, Player, SocialItem, TeamRef
from squad_screen.names import player_aliases

log = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_demo_bundle(team_query: str) -> dict:
    slug = team_query.strip().lower().replace(" ", "_")
    candidates = [
        FIXTURES_DIR / f"{slug}.json",
        FIXTURES_DIR / "barcelona.json",
    ]
    for path in candidates:
        if path.exists():
            log.info("Loading demo fixtures from %s", path.name)
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"No demo fixture for {team_query!r}")


def rebase_time(hours_ago: float, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now - timedelta(hours=hours_ago)


def demo_team(bundle: dict) -> TeamRef:
    t = bundle["team"]
    return TeamRef(
        id=str(t.get("id", "demo")),
        name=t["name"],
        short_name=t.get("short_name"),
        competition=t.get("competition"),
        venue=t.get("venue"),
        source="demo_fixture",
        crest_url=t.get("crest_url"),
    )


def demo_roster(bundle: dict) -> list[Player]:
    players: list[Player] = []
    for raw in bundle["roster"]:
        name = raw["name"]
        players.append(
            Player(
                id=str(raw["id"]),
                name=name,
                position=raw.get("position"),
                position_code=raw.get("position_code"),
                nationality=raw.get("nationality"),
                date_of_birth=raw.get("date_of_birth"),
                shirt_number=raw.get("shirt_number"),
                source="demo_fixture",
                aliases=player_aliases(name, raw.get("aliases") or []),
            )
        )
    return players


def demo_articles(bundle: dict, now: datetime | None = None) -> list[Article]:
    now = now or datetime.now(timezone.utc)
    articles: list[Article] = []
    for raw in bundle.get("articles", []):
        articles.append(
            Article(
                title=raw["title"],
                url=raw["url"],
                source=raw["source"],
                published_at=rebase_time(raw.get("hours_ago", 12), now),
                snippet=raw.get("snippet"),
                full_text=raw.get("full_text"),
                paywalled=bool(raw.get("paywalled")),
                player_mentions=raw.get("player_mentions") or [],
                fetch_status=raw.get("fetch_status", "fetched"),
                demo=True,
            )
        )
    return articles


def demo_social(bundle: dict, now: datetime | None = None) -> list[SocialItem]:
    now = now or datetime.now(timezone.utc)
    items: list[SocialItem] = []
    for raw in bundle.get("social", []):
        items.append(
            SocialItem(
                platform=raw["platform"],
                author=raw["author"],
                content=raw["content"],
                timestamp=rebase_time(raw.get("hours_ago", 8), now),
                url=raw.get("url"),
                media_type=raw.get("media_type", "post"),
                player_id=str(raw["player_id"]),
                player_name=raw["player_name"],
                fetch_status="demo_fixture",
                demo=True,
            )
        )
    return items
