from __future__ import annotations

import json
import logging
import re

from squad_screen.config import get_settings
from squad_screen.http import HttpClient
from squad_screen.models import Signal
from squad_screen.names import fold

log = logging.getLogger(__name__)

SYSTEM = """You classify lifestyle/readiness signals for football players.
You MUST only use the provided evidence text. Do not recall news from memory.
Do not invent players, quotes, articles, or posts.
Return JSON: {"signals":[{"player_name":str,"category":str,"severity":"low"|"medium"|"high","evidence":str}]}
evidence must be a verbatim substring of the provided text.
Categories: late_night_partying, alcohol, fatigue, injury, off_field_incident,
emotional_state, travel, rest, nutrition, conflict, readiness.
If nothing is supported by the text, return {"signals":[]}.
"""


def _evidence_in_source(evidence: str, source: str) -> bool:
    return fold(evidence.strip()) in fold(source) and len(evidence.strip()) >= 12


async def llm_enrich(
    client: HttpClient,
    chunks: list[tuple[str, str, str, str | None, str, bool]],
) -> list[Signal]:
    """chunks: (player_id, player_name, text, url, source_type, demo)"""
    settings = get_settings()
    if not settings.openai_api_key:
        return []
    signals: list[Signal] = []
    for player_id, player_name, text, url, source_type, demo in chunks:
        if not text or len(text) < 40:
            continue
        payload = {
            "model": settings.openai_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Player: {player_name}\n"
                        f"Text:\n{text[:6000]}"
                    ),
                },
            ],
        }
        response = await client.post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        )
        if response is None or response.status_code != 200:
            log.info("OpenAI classify skipped/failed: %s", getattr(response, "status_code", None))
            continue
        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (KeyError, json.JSONDecodeError, IndexError) as exc:
            log.info("OpenAI response unreadable: %s", exc)
            continue
        for raw in data.get("signals") or []:
            evidence = (raw.get("evidence") or "").strip()
            if not _evidence_in_source(evidence, text):
                continue
            severity = raw.get("severity")
            if severity not in {"low", "medium", "high"}:
                continue
            category = re.sub(r"[^a-z_]", "", (raw.get("category") or "").lower())
            if not category:
                continue
            signals.append(
                Signal(
                    player_id=player_id,
                    player_name=player_name,
                    category=category,
                    severity=severity,
                    evidence=evidence,
                    source_url=url,
                    source_type=source_type if source_type in {"article", "social", "reported_social"} else "article",
                    demo=demo,
                )
            )
    return signals
