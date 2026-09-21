from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse

import feedparser
import trafilatura
from dateutil import parser as dateparser

from squad_screen.config import get_settings
from squad_screen.http import HttpClient, looks_paywalled
from squad_screen.models import Article, CoverageGap, Player
from squad_screen.names import fold

log = logging.getLogger(__name__)

GOOGLE_NEWS = "https://news.google.com/rss/search?q={query}&hl=en-GB&gl=GB&ceid=GB:en"

SITE_FEEDS = [
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    ("The Guardian Football", "https://www.theguardian.com/football/rss"),
    ("ESPN FC", "https://www.espn.com/espn/rss/soccer/news"),
    ("Sky Sports Football", "https://www.skysports.com/rss/12040"),
]

NEWSAPI_URL = "https://newsapi.org/v2/everything"
GUARDIAN_URL = "https://content.guardianapis.com/search"
GNEWS_URL = "https://gnews.io/api/v4/search"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dateparser.parse(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        return None


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url


WEAK_ALIASES = {
    "man",
    "son",
    "van",
    "der",
    "den",
    "junior",
    "jr",
}


def match_players(text: str, players: list[Player]) -> list[str]:
    blob = fold(text)
    hits: list[str] = []
    for player in players:
        aliases = sorted(player.aliases or [player.name], key=len, reverse=True)
        for alias in aliases:
            token = fold(alias)
            if len(token) < 3:
                continue
            # Short / generic tokens ("Man") match "Man United" and must not count.
            if token in WEAK_ALIASES or (len(token) < 4 and token != fold(player.name)):
                continue
            if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", blob):
                hits.append(player.name)
                break
    return hits


def _within_window(published: datetime | None, start: datetime, end: datetime) -> bool:
    if published is None:
        return True
    return start <= published <= end


def _dedupe(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    out: list[Article] = []
    for article in articles:
        key = article.url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(article)
    return out


async def _parse_feed(client: HttpClient, url: str, source_name: str | None = None) -> list[Article]:
    response = await client.get(url)
    if response is None or response.status_code != 200:
        log.info("Feed unavailable %s (%s)", url, getattr(response, "status_code", None))
        return []
    parsed = feedparser.parse(response.text)
    items: list[Article] = []
    for entry in parsed.entries:
        link = entry.get("link") or ""
        title = entry.get("title") or ""
        if not link or not title:
            continue
        published = _parse_date(entry.get("published") or entry.get("updated"))
        snippet = ""
        if entry.get("summary"):
            snippet = re.sub(r"<[^>]+>", " ", entry.summary).strip()
        source = source_name or (entry.get("source", {}) or {}).get("title") or _host(link)
        items.append(
            Article(
                title=title,
                url=link,
                source=source,
                published_at=published,
                snippet=snippet[:500] or None,
                fetch_status="snippet_only",
            )
        )
    return items


async def collect_google_news(
    client: HttpClient, query: str
) -> list[Article]:
    url = GOOGLE_NEWS.format(query=quote_plus(query))
    return await _parse_feed(client, url, source_name=None)


async def collect_site_rss(client: HttpClient) -> tuple[list[Article], list[CoverageGap]]:
    articles: list[Article] = []
    gaps: list[CoverageGap] = []
    for name, url in SITE_FEEDS:
        items = await _parse_feed(client, url, source_name=name)
        if not items:
            gaps.append(
                CoverageGap(
                    area=f"news:{name}",
                    reason=f"RSS feed returned no items or was unreachable ({url}).",
                    impact="That outlet is missing from this run.",
                )
            )
        articles.extend(items)
    return articles, gaps


async def collect_newsapi(
    client: HttpClient, query: str, start: datetime
) -> tuple[list[Article], CoverageGap | None]:
    key = get_settings().newsapi_key
    if not key:
        return [], CoverageGap(
            area="news:NewsAPI",
            reason="NEWSAPI_KEY not set.",
            impact="Google News RSS and site feeds are used instead.",
        )
    response = await client.get(
        NEWSAPI_URL,
        params={
            "q": query,
            "from": start.date().isoformat(),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 50,
            "apiKey": key,
        },
    )
    if response is None or response.status_code != 200:
        return [], CoverageGap(
            area="news:NewsAPI",
            reason=f"NewsAPI request failed ({getattr(response, 'status_code', 'no response')}).",
            impact="Other news sources still apply.",
        )
    payload = response.json()
    if payload.get("status") != "ok":
        return [], CoverageGap(
            area="news:NewsAPI",
            reason=payload.get("message") or "NewsAPI returned an error.",
            impact="Other news sources still apply.",
        )
    articles: list[Article] = []
    for item in payload.get("articles") or []:
        articles.append(
            Article(
                title=item.get("title") or "",
                url=item.get("url") or "",
                source=(item.get("source") or {}).get("name") or _host(item.get("url") or ""),
                published_at=_parse_date(item.get("publishedAt")),
                snippet=item.get("description") or item.get("content"),
                fetch_status="snippet_only",
            )
        )
    return [a for a in articles if a.title and a.url], None


async def collect_guardian(
    client: HttpClient, query: str, start: datetime
) -> tuple[list[Article], CoverageGap | None]:
    key = get_settings().guardian_api_key
    if not key:
        return [], CoverageGap(
            area="news:Guardian",
            reason="GUARDIAN_API_KEY not set.",
            impact="Guardian Open Platform full text is skipped.",
        )
    response = await client.get(
        GUARDIAN_URL,
        params={
            "q": query,
            "from-date": start.date().isoformat(),
            "order-by": "newest",
            "page-size": 30,
            "show-fields": "bodyText,trailText,headline",
            "api-key": key,
        },
    )
    if response is None or response.status_code != 200:
        return [], CoverageGap(
            area="news:Guardian",
            reason=f"Guardian API failed ({getattr(response, 'status_code', 'no response')}).",
            impact="Guardian RSS may still contribute.",
        )
    payload = response.json()
    results = (payload.get("response") or {}).get("results") or []
    articles: list[Article] = []
    for item in results:
        fields = item.get("fields") or {}
        body = fields.get("bodyText")
        articles.append(
            Article(
                title=fields.get("headline") or item.get("webTitle") or "",
                url=item.get("webUrl") or "",
                source="The Guardian",
                published_at=_parse_date(item.get("webPublicationDate")),
                snippet=fields.get("trailText"),
                full_text=body,
                fetch_status="fetched" if body else "snippet_only",
            )
        )
    return [a for a in articles if a.title and a.url], None


async def collect_gnews(
    client: HttpClient, query: str, start: datetime
) -> tuple[list[Article], CoverageGap | None]:
    key = get_settings().gnews_api_key
    if not key:
        return [], CoverageGap(
            area="news:GNews",
            reason="GNEWS_API_KEY not set.",
            impact="GNews is skipped.",
        )
    response = await client.get(
        GNEWS_URL,
        params={
            "q": query,
            "from": start.isoformat(),
            "lang": "en",
            "max": 25,
            "token": key,
        },
    )
    if response is None or response.status_code != 200:
        return [], CoverageGap(
            area="news:GNews",
            reason=f"GNews failed ({getattr(response, 'status_code', 'no response')}).",
            impact="Other news sources still apply.",
        )
    articles: list[Article] = []
    for item in response.json().get("articles") or []:
        articles.append(
            Article(
                title=item.get("title") or "",
                url=item.get("url") or "",
                source=(item.get("source") or {}).get("name") or _host(item.get("url") or ""),
                published_at=_parse_date(item.get("publishedAt")),
                snippet=item.get("description"),
                fetch_status="snippet_only",
            )
        )
    return [a for a in articles if a.title and a.url], None


async def hydrate_article(client: HttpClient, article: Article) -> Article:
    if article.full_text:
        return article
    response = await client.get(article.url)
    if response is None:
        article.fetch_status = "inaccessible"
        return article
    html = response.text or ""
    if looks_paywalled(html, response.status_code):
        article.paywalled = True
        article.fetch_status = "paywalled"
        if not article.snippet:
            extracted = trafilatura.extract(html) or ""
            article.snippet = extracted[:400] or None
        return article
    text = trafilatura.extract(html) or ""
    if len(text.strip()) < 80:
        article.fetch_status = "inaccessible"
        article.snippet = article.snippet or text[:400] or None
        if looks_paywalled(html):
            article.paywalled = True
            article.fetch_status = "paywalled"
        return article
    article.full_text = text
    article.fetch_status = "fetched"
    if not article.snippet:
        article.snippet = text[:400]
    return article


def _player_queries(team: str, players: list[Player], cap: int = 18) -> list[str]:
    ranked = sorted(players, key=lambda p: (p.shirt_number is None, p.shirt_number or 99))
    queries = [f'"{team}" (football OR soccer) when:3d']
    for player in ranked[:cap]:
        queries.append(f'"{player.name}" {team} when:3d')
    return queries


async def collect_news(
    client: HttpClient,
    team_name: str,
    players: list[Player],
    start: datetime,
    end: datetime,
) -> tuple[list[Article], list[CoverageGap], list[str]]:
    attempted: list[str] = []
    gaps: list[CoverageGap] = []
    collected: list[Article] = []

    attempted.append("google-news-rss")
    queries = _player_queries(team_name, players)
    for query in queries:
        items = await collect_google_news(client, query)
        collected.extend(items)

    attempted.append("site-rss")
    rss_items, rss_gaps = await collect_site_rss(client)
    collected.extend(rss_items)
    gaps.extend(rss_gaps)

    attempted.append("newsapi")
    newsapi_items, newsapi_gap = await collect_newsapi(
        client, f"{team_name} football OR soccer", start
    )
    collected.extend(newsapi_items)
    if newsapi_gap:
        gaps.append(newsapi_gap)

    attempted.append("guardian")
    guardian_items, guardian_gap = await collect_guardian(client, team_name, start)
    collected.extend(guardian_items)
    if guardian_gap:
        gaps.append(guardian_gap)

    attempted.append("gnews")
    gnews_items, gnews_gap = await collect_gnews(client, f"{team_name} football", start)
    collected.extend(gnews_items)
    if gnews_gap:
        gaps.append(gnews_gap)

    windowed: list[Article] = []
    for article in _dedupe(collected):
        if not _within_window(article.published_at, start, end):
            continue
        blob = " ".join(filter(None, [article.title, article.snippet, article.full_text]))
        mentions = match_players(blob, players)
        if not mentions and team_name.lower() not in fold(blob):
            continue
        article.player_mentions = mentions
        if mentions or team_name.lower() in fold(blob):
            windowed.append(article)

    with_players = [a for a in windowed if a.player_mentions]
    team_only = [a for a in windowed if not a.player_mentions][:12]
    windowed = with_players[:80] + team_only

    # Prefer hydrating player-mention articles first
    windowed.sort(key=lambda a: (0 if a.player_mentions else 1, a.published_at or start))
    to_hydrate = windowed[:40]
    hydrated: list[Article] = []
    for article in to_hydrate:
        try:
            hydrated.append(await hydrate_article(client, article))
        except Exception as exc:  # noqa: BLE001
            log.debug("Hydrate failed for %s: %s", article.url, exc)
            article.fetch_status = "inaccessible"
            hydrated.append(article)
    remainder = windowed[40:]
    for article in remainder:
        article.fetch_status = "snippet_only"
    all_articles = hydrated + remainder
    for article in all_articles:
        blob = " ".join(filter(None, [article.title, article.snippet, article.full_text]))
        article.player_mentions = match_players(blob, players)

    if not all_articles:
        gaps.append(
            CoverageGap(
                area="news",
                reason="No in-window articles mentioning the team or its players were found.",
                impact="Signal analysis will rely only on social items, if any.",
            )
        )
    return all_articles, gaps, attempted
