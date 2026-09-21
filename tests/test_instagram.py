from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from squad_screen.config import get_settings, reset_settings_cache
from squad_screen.models import Player
from squad_screen.social import collect_social
from squad_screen.social.handles import load_handle_map, normalize_username
from squad_screen.social.instagram import classify_graph_error, collect_instagram

TOKEN = "test-token-not-real"
ACCOUNT_ID = "17841400000000000"


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class ScriptedClient:
    def __init__(self, responses: list[FakeResponse | None]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def get(self, url: str, *, headers=None, params=None, retries: int = 3):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        if not self._responses:
            return None
        return self._responses.pop(0)


def _player(pid: str = "8", name: str = "Pedri") -> Player:
    return Player(id=pid, name=name, source="test", aliases=[name])


def _iso(hours_ago: float = 2) -> str:
    stamp = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S+0000")


def _discovery_payload(
    username: str = "demo_pedri",
    media: list[dict] | None = None,
) -> dict:
    return {
        "business_discovery": {
            "username": username,
            "website": "https://example.invalid",
            "followers_count": 12,
            "media": {"data": media if media is not None else []},
            "id": "17841401111111111",
        },
        "id": ACCOUNT_ID,
    }


def _in_window_media(caption: str = "Recovery session at the gym.") -> dict:
    return {
        "id": "17858843269216389",
        "caption": caption,
        "media_type": "IMAGE",
        "permalink": "https://www.instagram.com/p/DEMO123/",
        "timestamp": _iso(3),
        "like_count": 4,
        "comments_count": 1,
    }


@pytest.fixture
def ig_env(monkeypatch, tmp_path: Path):
    handles = tmp_path / "instagram_handles.json"
    handles.write_text(json.dumps({"Pedri": "demo_pedri", "8": "demo_pedri"}), encoding="utf-8")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setenv("INSTAGRAM_HANDLES_FILE", str(handles))
    monkeypatch.setenv("INSTAGRAM_ENABLED", "true")
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
    reset_settings_cache()
    yield handles
    reset_settings_cache()


def test_normalize_username_strips_at_and_rejects_junk():
    assert normalize_username(" @Demo_Pedri ") == "Demo_Pedri"
    assert normalize_username("bad username") is None
    assert normalize_username("too)sneaky") is None
    assert normalize_username("") is None


def test_load_handle_map_json_and_csv(tmp_path: Path):
    json_path = tmp_path / "map.json"
    json_path.write_text(
        json.dumps(
            {
                "players": [
                    {"id": "10", "name": "Lamine Yamal", "username": "demo_lamineyamal"},
                ]
            }
        ),
        encoding="utf-8",
    )
    mapping = load_handle_map(json_path)
    yamal = _player("10", "Lamine Yamal")
    yamal.aliases = ["Yamal"]
    assert mapping.username_for(yamal) == "demo_lamineyamal"

    csv_path = tmp_path / "map.csv"
    csv_path.write_text("id,name,username\n8,Pedri,demo_pedri\n", encoding="utf-8")
    csv_map = load_handle_map(csv_path)
    assert csv_map.username_for(_player()) == "demo_pedri"

    missing = load_handle_map(tmp_path / "nope.json")
    assert missing.missing_file is True


@pytest.mark.asyncio
async def test_collect_instagram_success(ig_env, caplog):
    caplog.set_level(logging.DEBUG)
    start = datetime.now(timezone.utc) - timedelta(days=3)
    payload = _discovery_payload(media=[_in_window_media(), {
        "id": "old",
        "caption": "Last month",
        "media_type": "VIDEO",
        "permalink": "https://www.instagram.com/p/OLD/",
        "timestamp": (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S+0000"),
    }])
    client = ScriptedClient([FakeResponse(200, payload)])
    items, gaps = await collect_instagram(client, [_player()], start)
    assert len(items) == 1
    item = items[0]
    assert item.platform == "Instagram"
    assert item.player_name == "Pedri"
    assert item.player_id == "8"
    assert item.url == "https://www.instagram.com/p/DEMO123/"
    assert item.content == "Recovery session at the gym."
    assert item.author == "demo_pedri"
    assert item.media_type == "photo"
    assert item.fetch_status == "fetched"
    assert not any("rate limit" in g.reason.lower() for g in gaps)
    assert client.calls
    assert "v21.0" in client.calls[0]["url"]
    assert ACCOUNT_ID in client.calls[0]["url"]
    assert "business_discovery.username(demo_pedri)" in client.calls[0]["params"]["fields"]
    assert client.calls[0]["params"]["access_token"] == TOKEN
    assert TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_collect_instagram_empty_media(ig_env):
    start = datetime.now(timezone.utc) - timedelta(days=3)
    client = ScriptedClient([FakeResponse(200, _discovery_payload(media=[]))])
    items, gaps = await collect_instagram(client, [_player()], start)
    assert items == []
    assert any("no in-window media" in g.reason.lower() for g in gaps)


@pytest.mark.asyncio
async def test_collect_instagram_missing_handle_does_not_call_graph(ig_env):
    start = datetime.now(timezone.utc) - timedelta(days=3)
    client = ScriptedClient([FakeResponse(200, _discovery_payload())])
    unknown = _player("9", "Robert Lewandowski")
    items, gaps = await collect_instagram(client, [unknown], start)
    assert items == []
    assert client.calls == []
    assert any("no Instagram username mapping" in g.reason for g in gaps)
    assert "Robert Lewandowski" in gaps[0].reason


@pytest.mark.asyncio
async def test_collect_instagram_personal_account_error(ig_env):
    start = datetime.now(timezone.utc) - timedelta(days=3)
    client = ScriptedClient(
        [
            FakeResponse(
                400,
                {
                    "error": {
                        "message": "The user is not an Instagram Business account.",
                        "type": "OAuthException",
                        "code": 100,
                    }
                },
            )
        ]
    )
    items, gaps = await collect_instagram(client, [_player()], start)
    assert items == []
    assert any("personal" in g.reason.lower() or "professional" in g.reason.lower() for g in gaps)


@pytest.mark.asyncio
async def test_collect_instagram_not_found_and_oauth(ig_env):
    start = datetime.now(timezone.utc) - timedelta(days=3)
    not_found = FakeResponse(
        400,
        {
            "error": {
                "message": "Invalid user id",
                "type": "OAuthException",
                "code": 100,
                "error_subcode": 2207013,
            }
        },
    )
    client = ScriptedClient([not_found])
    items, gaps = await collect_instagram(client, [_player()], start)
    assert items == []
    assert any("personal" in g.reason.lower() or "not exist" in g.reason.lower() for g in gaps)

    client = ScriptedClient(
        [
            FakeResponse(
                403,
                {"error": {"message": "Invalid OAuth access token.", "type": "OAuthException", "code": 190}},
            )
        ]
    )
    items, gaps = await collect_instagram(client, [_player()], start)
    assert items == []
    assert any("rejected the credentials" in g.reason for g in gaps)


@pytest.mark.asyncio
async def test_collect_instagram_rate_limit_stops_remaining(monkeypatch, tmp_path: Path, caplog):
    caplog.set_level(logging.INFO)
    handles = tmp_path / "instagram_handles.json"
    handles.write_text(
        json.dumps({"Pedri": "demo_pedri", "Gavi": "demo_gavi"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ACCOUNT_ID)
    monkeypatch.setenv("INSTAGRAM_HANDLES_FILE", str(handles))
    reset_settings_cache()
    start = datetime.now(timezone.utc) - timedelta(days=3)
    client = ScriptedClient(
        [
            FakeResponse(429, {"error": {"message": "Application request limit reached", "code": 4}}),
            FakeResponse(200, _discovery_payload("demo_gavi", [_in_window_media()])),
        ]
    )
    items, gaps = await collect_instagram(
        client, [_player(), _player("6", "Gavi")], start
    )
    assert items == []
    assert len(client.calls) == 1
    assert any("rate limit" in g.reason.lower() for g in gaps)
    assert TOKEN not in caplog.text
    reset_settings_cache()


@pytest.mark.asyncio
async def test_collect_instagram_skipped_without_env(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("INSTAGRAM_HANDLES_FILE", str(tmp_path / "missing.json"))
    reset_settings_cache()
    client = ScriptedClient([FakeResponse(200, _discovery_payload())])
    items, gaps = await collect_instagram(
        client, [_player()], datetime.now(timezone.utc) - timedelta(days=3)
    )
    assert items == []
    assert client.calls == []
    assert any("INSTAGRAM_ACCESS_TOKEN" in g.reason for g in gaps)
    reset_settings_cache()


@pytest.mark.asyncio
async def test_collect_social_merges_instagram_without_breaking_twitter_gap(ig_env):
    start = datetime.now(timezone.utc) - timedelta(days=3)
    client = ScriptedClient(
        [FakeResponse(200, _discovery_payload(media=[_in_window_media("Full training. See you tomorrow.")]))]
    )
    items, gaps, attempted = await collect_social(client, [_player()], [], start)
    assert "instagram-business-discovery" in attempted
    assert "x-twitter-recent-search" in attempted
    assert any(i.platform == "Instagram" for i in items)
    assert any(g.area == "social:X/Twitter" for g in gaps)
    assert not any("Basic Display" in g.reason for g in gaps)


def test_classify_graph_error_kinds():
    kind, message = classify_graph_error(
        400, {"message": "(#100) Tried accessing nonexisting field (business_discovery) on node type (User)", "code": 100}
    )
    assert kind == "observer"
    assert "professional" in message.lower() or "IG User" in message
    kind, message = classify_graph_error(400, {"message": "Cannot find user", "error_subcode": 2207013})
    assert kind == "not_found"
    assert "personal" in message.lower()


def test_settings_instagram_ready(ig_env):
    settings = get_settings()
    assert settings.instagram_ready is True
    assert settings.instagram_graph_version == "v21.0"
    assert settings.instagram_max_players == 20
    assert settings.instagram_max_media == 10
