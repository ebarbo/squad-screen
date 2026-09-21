from __future__ import annotations

import re
import unicodedata

POSITION_CODES = ("GK", "RB", "CB", "LB", "WB", "DM", "CM", "AM", "RW", "LW", "ST")

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("GK", ("goalkeeper", "goalie", "gk", "keeper")),
    ("RB", ("right-back", "right back", "rightback", "rb", "right full")),
    ("LB", ("left-back", "left back", "leftback", "lb", "left full")),
    ("WB", ("wing-back", "wingback", "wing back", "rwb", "lwb")),
    ("CB", ("centre-back", "center-back", "centre back", "center back", "central defender", "cb")),
    ("DM", ("defensive mid", "defensive midfielder", "holding", "dm", "cdm")),
    ("AM", ("attacking mid", "attacking midfielder", "playmaker", "am", "cam", "number 10")),
    ("CM", ("central mid", "centre mid", "center mid", "midfielder", "midfield", "cm")),
    ("RW", ("right winger", "right wing", "rw")),
    ("LW", ("left winger", "left wing", "lw")),
    ("ST", ("striker", "centre-forward", "center-forward", "centre forward", "forward", "cf", "st")),
]


def fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def normalize_position(raw: str | None) -> str | None:
    if not raw:
        return None
    key = fold(raw).strip()
    shorthand = {
        "gk": "GK",
        "df": "CB",
        "mf": "CM",
        "fw": "ST",
        "g": "GK",
    }
    if key in shorthand:
        return shorthand[key]
    for code, needles in _RULES:
        if any(needle == key or needle in key for needle in needles):
            return code
    if "defen" in key:
        return "CB"
    if "mid" in key:
        return "CM"
    if "wing" in key:
        return "RW"
    if "attack" in key or "forward" in key:
        return "ST"
    return None


def group_for(code: str | None) -> str:
    if code == "GK":
        return "GK"
    if code in {"RB", "CB", "LB", "WB"}:
        return "DEF"
    if code in {"DM", "CM", "AM"}:
        return "MID"
    return "FWD"


def last_name(full_name: str) -> str:
    parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if not parts:
        return full_name
    particles = {"de", "da", "do", "del", "della", "van", "von", "di", "la", "le"}
    if len(parts) >= 2 and fold(parts[-2]) in particles:
        return " ".join(parts[-2:])
    return parts[-1]


def player_aliases(name: str, extra: list[str] | None = None) -> list[str]:
    aliases = {name, last_name(name)}
    for item in extra or []:
        if item:
            aliases.add(item)
    return [a for a in aliases if len(a) >= 3]
