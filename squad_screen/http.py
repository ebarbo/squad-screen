from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from squad_screen.config import get_settings

log = logging.getLogger(__name__)

PAYWALL_MARKERS = (
    "subscribe to continue",
    "subscription to read",
    "become a subscriber",
    "this article is for subscribers",
    "paywall",
    "piano-paywall",
    "already a subscriber",
    "sign in to read",
    "create an account to continue",
    "for subscribers only",
)


class HttpClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._timeout = httpx.Timeout(settings.http_timeout_seconds, connect=10.0)
        self._headers = {"User-Agent": settings.http_user_agent}
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers=self._headers,
            follow_redirects=True,
        )
        self._sem = asyncio.Semaphore(max(2, settings.news_concurrency))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> httpx.Response | None:
        merged = {**self._headers, **(headers or {})}
        async with self._sem:
            last_exc: Exception | None = None
            for attempt in range(retries):
                try:
                    response = await self._client.get(url, headers=merged, params=params)
                    if response.status_code == 429:
                        wait = 2 ** attempt
                        log.warning("Rate limited on %s; sleeping %ss", url, wait)
                        await asyncio.sleep(wait)
                        continue
                    return response
                except httpx.HTTPError as exc:
                    last_exc = exc
                    wait = 2 ** attempt
                    log.debug("HTTP error %s on %s; retry in %ss", exc, url, wait)
                    await asyncio.sleep(wait)
            log.warning("Giving up on %s (%s)", url, last_exc)
            return None

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response | None:
        merged = {**self._headers, **(headers or {})}
        try:
            return await self._client.post(url, json=payload, headers=merged)
        except httpx.HTTPError as exc:
            log.warning("POST failed %s: %s", url, exc)
            return None


def looks_paywalled(html: str, status_code: int | None = None) -> bool:
    if status_code in {401, 402, 403}:
        return True
    lowered = html.lower()
    return any(marker in lowered for marker in PAYWALL_MARKERS)
