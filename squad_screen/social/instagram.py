"""Instagram collection via Meta Graph API Business Discovery only.

Requires a long-lived User access token and the observer professional account's
IG user id. Other accounts are read by explicit username mapping — never by
name search, HTML scraping, or unofficial APIs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from dateutil import parser as dateparser

from squad_screen.config import get_settings
from squad_screen.http import HttpClient
from squad_screen.models import CoverageGap, Player, SocialItem
from squad_screen.social.handles import load_handle_map, normalize_username

log = logging.getLogger(__name__)

GRAPH_HOST = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v21.0"
VERSION_RE = re.compile(r"^v\d+\.\d+$")
ACCOUNT_ID_RE = re.compile(r"^\d+$")

# Graph error codes commonly returned for auth, permission, and rate limits.
OAUTH_CODES = {102, 190, 467}
PERMISSION_CODES = {10, 200, 294}
RATE_LIMIT_CODES = {4, 17, 32, 613, 80004}
# Instagram-specific "cannot find user" / invalid target subcodes.
NOT_FOUND_SUBCODES = {2207013, 2207018, 2207027, 2207004}

MEDIA_TYPE_MAP = {
    "IMAGE": "photo",
    "VIDEO": "video",
    "CAROUSEL_ALBUM": "carousel",
}

PERSONAL_HINTS = (
    "personal account",
    "not a business",
    "not an instagram business",
    "not a professional",
    "instagram user is not a business",
    "only business and creator",
    "professional accounts only",
)
NOT_FOUND_HINTS = (
    "cannot find user",
    "invalid user id",
    "user not found",
    "does not exist",
    "tried accessing nonexisting field (username)",
)


async def collect_instagram(
    client: HttpClient,
    players: list[Player],
    start: datetime,
) -> tuple[list[SocialItem], list[CoverageGap]]:
    settings = get_settings()
    if not settings.instagram_enabled:
        return [], [
            CoverageGap(
                area="social:Instagram",
                reason="INSTAGRAM_ENABLED is false; Instagram Business Discovery was skipped.",
                impact="First-party Instagram posts are not collected. Second-hand mentions in news may still appear.",
            )
        ]
    if not settings.instagram_ready:
        missing = []
        if not settings.instagram_access_token.strip():
            missing.append("INSTAGRAM_ACCESS_TOKEN")
        if not settings.instagram_business_account_id.strip():
            missing.append("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        return [], [
            CoverageGap(
                area="social:Instagram",
                reason=(
                    f"{' and '.join(missing)} not set. Instagram Business Discovery "
                    "is not used. There is no public unauthenticated feed and scraping is out of scope."
                ),
                impact="First-party Instagram posts, stories, and check-ins are not collected.",
            )
        ]

    account_id = settings.instagram_business_account_id.strip()
    if not ACCOUNT_ID_RE.fullmatch(account_id):
        return [], [
            CoverageGap(
                area="social:Instagram",
                reason=(
                    "INSTAGRAM_BUSINESS_ACCOUNT_ID must be the numeric Instagram professional "
                    "(IG User) id of the observer account making Business Discovery queries."
                ),
                impact="Instagram collection did not run.",
            )
        ]

    handle_map = load_handle_map(settings.instagram_handles_file)
    if handle_map.missing_file:
        return [], [
            CoverageGap(
                area="social:Instagram",
                reason=(
                    f"No Instagram handle map at {settings.instagram_handles_file}. "
                    "Business Discovery can only look up explicit usernames — there is no "
                    "free-text search for players by name. Copy config/instagram_handles.example.json."
                ),
                impact="Instagram was not queried for any player.",
            )
        ]

    mapped: list[tuple[Player, str]] = []
    unmapped: list[str] = []
    for player in players:
        username = handle_map.username_for(player)
        if username:
            mapped.append((player, username))
        else:
            unmapped.append(player.name)

    gaps: list[CoverageGap] = []
    if unmapped:
        gaps.append(
            CoverageGap(
                area="social:Instagram",
                reason=(
                    f"{len(unmapped)} of {len(players)} roster player(s) have no Instagram "
                    f"username mapping ({_name_list(unmapped)}). Handles are never invented."
                ),
                impact="Those players are omitted from Instagram Business Discovery.",
            )
        )

    max_players = max(0, settings.instagram_max_players)
    over_cap = mapped[max_players:]
    to_fetch = mapped[:max_players]
    if over_cap:
        gaps.append(
            CoverageGap(
                area="social:Instagram",
                reason=(
                    f"Instagram player cap (INSTAGRAM_MAX_PLAYERS={max_players}) skipped "
                    f"{len(over_cap)} mapped player(s) ({_name_list([p.name for p, _ in over_cap])})."
                ),
                impact="Raise INSTAGRAM_MAX_PLAYERS to query more mapped professional accounts.",
            )
        )

    if not to_fetch:
        if not gaps:
            gaps.append(
                CoverageGap(
                    area="social:Instagram",
                    reason="Handle map loaded but no roster player matched an Instagram username.",
                    impact="Instagram was not queried.",
                )
            )
        return [], gaps

    version = _graph_version(settings.instagram_graph_version)
    media_limit = max(1, settings.instagram_max_media)
    token = settings.instagram_access_token.strip()
    items: list[SocialItem] = []
    empty_media: list[str] = []
    stopped = False

    for player, username in to_fetch:
        if stopped:
            break
        response = await _discover(client, version, account_id, username, media_limit, token)
        if response is None:
            gaps.append(
                CoverageGap(
                    area="social:Instagram",
                    reason=(
                        f"No HTTP response for @{username} ({player.name}). "
                        "The request failed after retries; nothing was invented."
                    ),
                    impact="That player's Instagram feed is missing from this report.",
                )
            )
            continue

        payload = _json_body(response)
        error = payload.get("error") if isinstance(payload, dict) else None
        if response.status_code != 200 or error:
            kind, message = classify_graph_error(response.status_code, error if isinstance(error, dict) else None)
            log.info(
                "Instagram Business Discovery for %s (@%s): HTTP %s (%s)",
                player.name,
                username,
                response.status_code,
                kind,
            )
            if kind == "rate_limit":
                remaining = [p.name for p, _ in to_fetch[to_fetch.index((player, username)) :]]
                gaps.append(
                    CoverageGap(
                        area="social:Instagram",
                        reason=(
                            f"Graph API rate limit while reading @{username}. "
                            f"Stopped remaining Instagram lookups ({_name_list(remaining)})."
                        ),
                        impact="Partial Instagram coverage. Later players were not queried.",
                    )
                )
                stopped = True
                break
            if kind in {"auth", "observer"}:
                gaps.append(
                    CoverageGap(
                        area="social:Instagram",
                        reason=message,
                        impact="Instagram collection stopped. Check token, permissions, and observer IG user id.",
                    )
                )
                stopped = True
                break
            gaps.append(
                CoverageGap(
                    area="social:Instagram",
                    reason=f"{player.name} (@{username}): {message}",
                    impact="No first-party Instagram items for this player.",
                )
            )
            continue

        discovery = payload.get("business_discovery") if isinstance(payload, dict) else None
        if not isinstance(discovery, dict):
            gaps.append(
                CoverageGap(
                    area="social:Instagram",
                    reason=(
                        f"{player.name} (@{username}): Business Discovery returned no account object. "
                        "The username may be wrong, personal, or age-gated."
                    ),
                    impact="No first-party Instagram items for this player.",
                )
            )
            continue

        author = normalize_username(str(discovery.get("username") or username)) or username
        media_rows = ((discovery.get("media") or {}).get("data")) if isinstance(discovery.get("media"), dict) else []
        kept = 0
        for media in media_rows or []:
            if not isinstance(media, dict):
                continue
            item = _media_item(player, author, media, start)
            if item is None:
                continue
            items.append(item)
            kept += 1
        if kept == 0:
            empty_media.append(f"{player.name} (@{username})")

    if empty_media:
        gaps.append(
            CoverageGap(
                area="social:Instagram",
                reason=(
                    f"Business Discovery returned no in-window media for {len(empty_media)} "
                    f"mapped account(s) ({_name_list(empty_media)}). Empty feeds are not filled in."
                ),
                impact="Those players have no first-party Instagram items in this window.",
            )
        )
    return items, gaps


def classify_graph_error(
    status_code: int,
    error: dict | None,
) -> tuple[str, str]:
    """Map Graph HTTP/JSON errors to a stable kind + coverage-safe message (never includes tokens)."""
    error = error or {}
    code = error.get("code")
    subcode = error.get("error_subcode")
    raw_message = str(error.get("message") or "")
    lowered = raw_message.lower()
    err_type = str(error.get("type") or "")

    if status_code == 429 or code in RATE_LIMIT_CODES:
        return "rate_limit", "Graph API rate limit (HTTP 429 or code 4/17/32/613)."
    if status_code in {401, 403} or code in OAUTH_CODES or code in PERMISSION_CODES:
        return "auth", (
            "Instagram Graph API rejected the credentials (HTTP "
            f"{status_code}, OAuth/permission error). Token may be expired, "
            "missing instagram_basic / instagram_manage_insights / pages_read_engagement, "
            "or the app may still be in Development without Advanced Access."
        )
    if "nonexisting field" in lowered and "business_discovery" in lowered:
        return "observer", (
            "INSTAGRAM_BUSINESS_ACCOUNT_ID is not an Instagram professional (IG User) account, "
            "or the token cannot use Business Discovery on it. Personal Facebook User ids will not work."
        )
    if any(hint in lowered for hint in PERSONAL_HINTS):
        return "personal", (
            "Instagram Business Discovery can only read other Business/Creator (professional) "
            "accounts. This username looks like a personal account and cannot be fetched."
        )
    if subcode in NOT_FOUND_SUBCODES or any(hint in lowered for hint in NOT_FOUND_HINTS):
        return "not_found", (
            "Username was not returned by Business Discovery. The account may not exist, "
            "may be a personal (non-professional) account, or may be age-gated. "
            "Personal accounts cannot be fetched."
        )
    if status_code in {400, 404}:
        return "not_found", (
            f"Graph API HTTP {status_code} for this username. "
            "Treat as missing, personal, or unreadable by Business Discovery — nothing was invented."
        )
    snippet = raw_message.strip() or err_type or f"HTTP {status_code}"
    # Keep coverage notes short and token-free.
    snippet = re.sub(r"access_token=[^&\s]+", "access_token=[redacted]", snippet)[:240]
    return "error", f"Graph API error ({snippet})."


def parse_instagram_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = dateparser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _discover(
    client: HttpClient,
    version: str,
    account_id: str,
    username: str,
    media_limit: int,
    token: str,
):
    media_fields = "id,caption,media_type,permalink,timestamp,like_count,comments_count"
    user_fields = (
        f"username,website,followers_count,media.limit({media_limit})"
        f"{{{media_fields}}}"
    )
    fields = f"business_discovery.username({username}){{{user_fields}}}"
    url = f"{GRAPH_HOST}/{version}/{account_id}"
    return await client.get(
        url,
        params={"fields": fields, "access_token": token},
    )


def _media_item(
    player: Player,
    author: str,
    media: dict,
    start: datetime,
) -> SocialItem | None:
    timestamp = parse_instagram_timestamp(media.get("timestamp") if isinstance(media.get("timestamp"), str) else None)
    if timestamp is None:
        return None
    if timestamp < start.astimezone(timezone.utc):
        return None
    caption = media.get("caption")
    text = caption if isinstance(caption, str) else ""
    permalink = media.get("permalink") if isinstance(media.get("permalink"), str) else None
    raw_type = str(media.get("media_type") or "").upper()
    media_type = MEDIA_TYPE_MAP.get(raw_type, "post")
    if not text and not permalink and not media.get("id"):
        return None
    return SocialItem(
        platform="Instagram",
        author=author,
        content=text,
        timestamp=timestamp,
        url=permalink,
        media_type=media_type,
        player_id=player.id,
        player_name=player.name,
        fetch_status="fetched",
    )


def _graph_version(raw: str | None) -> str:
    value = (raw or DEFAULT_GRAPH_VERSION).strip()
    if VERSION_RE.fullmatch(value):
        return value
    log.info("Ignoring invalid INSTAGRAM_GRAPH_VERSION %r; using %s", raw, DEFAULT_GRAPH_VERSION)
    return DEFAULT_GRAPH_VERSION


def _json_body(response) -> dict:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _name_list(names: list[str], limit: int = 8) -> str:
    if not names:
        return "none"
    if len(names) <= limit:
        return ", ".join(names)
    extra = len(names) - limit
    return f"{', '.join(names[:limit])}, and {extra} more"
