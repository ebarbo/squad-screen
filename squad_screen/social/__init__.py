from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from squad_screen.config import get_settings
from squad_screen.http import HttpClient
from squad_screen.models import Article, CoverageGap, Player, SocialItem
from squad_screen.names import fold

log = logging.getLogger(__name__)

TWITTER_SEARCH = "https://api.twitter.com/2/tweets/search/recent"

REPORTED_SOCIAL = re.compile(
    r"(posted|shared|uploaded|uploaded a|went live|checked in|stories?)\s+"
    r"(on|to|via)?\s*(instagram|twitter|x\.com|\bx\b|tiktok|facebook|snapchat)",
    re.I,
)


PLATFORM_GAPS = [
    CoverageGap(
        area="social:Instagram",
        reason="Instagram Graph/Basic Display requires an approved Meta app and user tokens; no unauthenticated public feed is used.",
        impact="First-party Instagram posts, stories, and check-ins are not collected.",
    ),
    CoverageGap(
        area="social:TikTok",
        reason="TikTok Display/Research APIs require app review; unofficial scraping is not used.",
        impact="First-party TikTok videos are not collected.",
    ),
    CoverageGap(
        area="social:Facebook",
        reason="Facebook Graph API requires Page tokens; personal profiles are not publicly enumerable.",
        impact="First-party Facebook posts are not collected.",
    ),
]


async def collect_twitter(
    client: HttpClient,
    players: list[Player],
    start: datetime,
) -> tuple[list[SocialItem], CoverageGap | None]:
    token = get_settings().twitter_bearer_token
    if not token:
        return [], CoverageGap(
            area="social:X/Twitter",
            reason="TWITTER_BEARER_TOKEN not set.",
            impact="No first-party tweets are collected. Second-hand mentions in news may still appear.",
        )
    headers = {"Authorization": f"Bearer {token}"}
    items: list[SocialItem] = []
    for player in players[:20]:
        query = f'"{player.name}" -is:retweet'
        response = await client.get(
            TWITTER_SEARCH,
            headers=headers,
            params={
                "query": query,
                "max_results": 10,
                "start_time": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tweet.fields": "created_at,author_id,text",
            },
        )
        if response is None:
            continue
        if response.status_code != 200:
            log.info("Twitter search for %s: HTTP %s", player.name, response.status_code)
            continue
        for tweet in response.json().get("data") or []:
            tid = tweet.get("id")
            items.append(
                SocialItem(
                    platform="X",
                    author=str(tweet.get("author_id") or "unknown"),
                    content=tweet.get("text") or "",
                    timestamp=_parse_ts(tweet.get("created_at")),
                    url=f"https://x.com/i/web/status/{tid}" if tid else None,
                    media_type="post",
                    player_id=player.id,
                    player_name=player.name,
                    fetch_status="fetched",
                )
            )
    return items, None


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_reported_social(articles: list[Article], players: list[Player]) -> list[SocialItem]:
    """Second-hand social appearances mentioned in articles. Not first-party posts."""
    items: list[SocialItem] = []
    for article in articles:
        text = " ".join(filter(None, [article.title, article.snippet, article.full_text]))
        if not text:
            continue
        for match in REPORTED_SOCIAL.finditer(text):
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 180)
            snippet = re.sub(r"\s+", " ", text[start:end]).strip()
            platform = match.group(3)
            if fold(platform) in {"x", "x.com", "twitter"}:
                platform = "X"
            else:
                platform = platform.capitalize()
            mentioned = article.player_mentions or []
            if not mentioned:
                continue
            for name in mentioned:
                player = next((p for p in players if p.name == name), None)
                if not player:
                    continue
                items.append(
                    SocialItem(
                        platform=platform,
                        author=name,
                        content=f"[Reported in {article.source}] {snippet}",
                        timestamp=article.published_at,
                        url=article.url,
                        media_type="reported_mention",
                        player_id=player.id,
                        player_name=player.name,
                        fetch_status="second_hand",
                    )
                )
    return items


async def collect_social(
    client: HttpClient,
    players: list[Player],
    articles: list[Article],
    start: datetime,
) -> tuple[list[SocialItem], list[CoverageGap], list[str]]:
    attempted = ["x-twitter-recent-search", "reported-social-from-news"]
    gaps = list(PLATFORM_GAPS)
    tweets, twitter_gap = await collect_twitter(client, players, start)
    if twitter_gap:
        gaps.append(twitter_gap)
    reported = extract_reported_social(articles, players)
    items = tweets + reported
    if not items:
        gaps.append(
            CoverageGap(
                area="social",
                reason="No first-party or second-hand social items were collected in the window.",
                impact="Lifestyle signals will come only from news text, if any.",
            )
        )
    return items, gaps, attempted
