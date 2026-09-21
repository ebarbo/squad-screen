"""Explicit Instagram username mappings. Handles are never inferred from player names."""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from squad_screen.models import Player
from squad_screen.names import fold

log = logging.getLogger(__name__)

# Instagram usernames: letters, digits, periods, underscores; 1–30 chars.
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def normalize_username(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    value = raw.strip().lstrip("@")
    if not USERNAME_RE.fullmatch(value):
        return None
    return value


@dataclass
class HandleMap:
    by_id: dict[str, str] = field(default_factory=dict)
    by_name: dict[str, str] = field(default_factory=dict)
    path: Path | None = None
    missing_file: bool = False

    def username_for(self, player: Player) -> str | None:
        if player.id and player.id in self.by_id:
            return self.by_id[player.id]
        folded = fold(player.name)
        if folded in self.by_name:
            return self.by_name[folded]
        for alias in player.aliases or []:
            key = fold(alias)
            if key in self.by_name:
                return self.by_name[key]
        return None

    def add(self, username: str | None, *, player_id: str | None = None, name: str | None = None) -> None:
        handle = normalize_username(username)
        if not handle:
            if username:
                log.info("Ignoring invalid Instagram username %r", username)
            return
        if player_id and str(player_id).strip():
            self.by_id[str(player_id).strip()] = handle
        if name and str(name).strip():
            self.by_name[fold(str(name))] = handle


def load_handle_map(path: str | Path | None) -> HandleMap:
    if not path:
        return HandleMap(missing_file=True)
    file_path = Path(path)
    if not file_path.is_file():
        log.info("Instagram handle map not found at %s", file_path)
        return HandleMap(path=file_path, missing_file=True)
    suffix = file_path.suffix.lower()
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("Could not read Instagram handle map %s: %s", file_path, exc)
        return HandleMap(path=file_path, missing_file=True)
    mapping = HandleMap(path=file_path, missing_file=False)
    if suffix == ".csv":
        _load_csv(mapping, text)
    else:
        _load_json(mapping, text)
    log.info(
        "Loaded Instagram handle map from %s (%s id keys, %s name keys)",
        file_path.name,
        len(mapping.by_id),
        len(mapping.by_name),
    )
    return mapping


def _load_json(mapping: HandleMap, text: str) -> None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("Instagram handle map is not valid JSON: %s", exc)
        return
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                mapping.add(row.get("username"), player_id=row.get("id"), name=row.get("name"))
        return
    if not isinstance(data, dict):
        log.warning("Instagram handle map must be a JSON object, list, or CSV.")
        return
    players = data.get("players")
    if isinstance(players, list):
        for row in players:
            if isinstance(row, dict):
                mapping.add(row.get("username"), player_id=row.get("id"), name=row.get("name"))
        return
    for key, value in data.items():
        if not isinstance(key, str) or key.startswith("_"):
            continue
        if isinstance(value, dict):
            mapping.add(
                value.get("username"),
                player_id=value.get("id") or key,
                name=value.get("name") or key,
            )
        elif isinstance(value, str):
            # Key may be a roster id or a display name.
            mapping.add(value, player_id=key, name=key)


def _load_csv(mapping: HandleMap, text: str) -> None:
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        return
    for row in reader:
        mapping.add(
            row.get("username") or row.get("handle") or row.get("instagram"),
            player_id=row.get("id") or row.get("player_id"),
            name=row.get("name") or row.get("player_name"),
        )
