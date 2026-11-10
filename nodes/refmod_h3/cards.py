"""Character Card V2 parsing/normalisation (local copy of the LLM/cards family rules,
so this package has no import-time dependency on it). Pure logic.
"""
from __future__ import annotations

import copy
import json
import re

from ._types import JSONDict, JSONValue, RefModError

V2_DEFAULTS: JSONDict = {
    "name": "", "description": "", "personality": "", "scenario": "", "first_mes": "", "mes_example": "",
    "creator_notes": "", "system_prompt": "", "post_history_instructions": "", "alternate_greetings": [],
    "tags": [], "creator": "", "character_version": "", "extensions": {},
}
STRING_FIELDS = tuple(k for k, v in V2_DEFAULTS.items() if isinstance(v, str))
HINT_KEYS = ("name", "description", "first_mes", "personality")
LEGACY_KEYS = {
    "char_name": "name", "char_persona": "description", "world_scenario": "scenario",
    "char_greeting": "first_mes", "example_dialogue": "mes_example",
}
DESCEND_KEYS = ("character", "card", "char", "result", "output", "json")
_FENCE = re.compile(r"^```[\w-]*\s*\n?(.*?)\n?```\s*$", re.S)
_UNSAFE = re.compile(r'[\\/:*?"<>|%\x00-\x1f\x7f]')


def _loads(text: str) -> JSONValue:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        start = max(0, exc.pos - 40)
        snippet = text[start: exc.pos + 20].replace("\n", " ")
        raise RefModError(f"card JSON is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg} "
                          f"near ...{snippet}...") from exc


def _lower_keys(d: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {str(k).lower(): v for k, v in d.items()}


def parse_card(text: str, fill_missing: bool = True) -> tuple[JSONDict, list[str]]:
    """Parse pasted JSON into a Character Card V2 dict. Returns (card, repair notes)."""
    s = str(text or "").lstrip("﻿").strip()
    m = _FENCE.match(s)
    if m:
        s = m.group(1).strip()
    if not s:
        raise RefModError("card JSON is empty")
    notes: list[str] = []
    value: JSONValue = _loads(s)
    for _ in range(5):
        if isinstance(value, str):
            try:
                value = json.loads(value)
                notes.append("decoded double-encoded JSON")
                continue
            except json.JSONDecodeError:
                break
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
            notes.append("unwrapped a one-item list")
            continue
        if not isinstance(value, dict):
            break
        value = _lower_keys(value)
        data = value.get("data")
        if isinstance(data, str):
            try:
                value["data"] = data = json.loads(data)
                notes.append("decoded string 'data'")
            except json.JSONDecodeError:
                pass
        if isinstance(data, dict):
            value["data"] = _lower_keys(data)
            break
        if any(k in value for k in HINT_KEYS):
            break
        legacy = [k for k in LEGACY_KEYS if k in value]
        if legacy:
            for k in legacy:
                value[LEGACY_KEYS[k]] = value.pop(k)
            notes.append("renamed legacy TavernAI keys")
            break
        nxt = next((value[k] for k in DESCEND_KEYS if isinstance(value.get(k), (dict, str))), None)
        if nxt is None and len(value) == 1:
            nxt = next(iter(value.values()))
        if nxt is None:
            break
        value = nxt
        notes.append("descended into a wrapper object")
    if not isinstance(value, dict):
        raise RefModError("card JSON must be an object")
    if isinstance(value.get("data"), dict):
        spec = value.get("spec")
        if spec == "chara_card_v3":
            notes.append("relabelled chara_card_v3 as chara_card_v2")
        elif spec not in (None, "chara_card_v2"):
            notes.append(f"replaced unknown spec {spec!r}")
        extra = {k: v for k, v in value.items() if k not in ("spec", "spec_version", "data")}
        card: JSONDict = {"spec": "chara_card_v2", "spec_version": "2.0", "data": dict(value["data"]), **extra}  # type: ignore[arg-type]
    elif any(k in value for k in HINT_KEYS):
        card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": dict(value)}
        notes.append("wrapped a flat card as V2 data")
    else:
        keys = ", ".join(list(value)[:12])
        raise RefModError(f"no character card found; top-level keys: {keys}")
    data = card["data"]
    assert isinstance(data, dict)
    if fill_missing:
        for k, v in V2_DEFAULTS.items():
            if data.get(k) is None:
                data[k] = copy.deepcopy(v)
    for k in STRING_FIELDS:
        if k in data and not isinstance(data[k], str):
            data[k] = "" if data[k] is None else str(data[k])
    if isinstance(data.get("tags"), str):
        data["tags"] = [t.strip() for t in str(data["tags"]).split(",") if t.strip()]
    if isinstance(data.get("alternate_greetings"), str):
        data["alternate_greetings"] = [data["alternate_greetings"]]
    if "extensions" in data and not isinstance(data["extensions"], dict):
        data["extensions"] = {}
    if not str(data.get("name") or "").strip():
        raise RefModError("card has no name (data.name is blank)")
    return card, notes


def safe_name(name: str) -> str:
    s = _UNSAFE.sub("_", str(name or "")).strip(" .")[:80].strip(" .")
    return s or "card"


def _text_len(v: JSONValue) -> int:
    return len(v) if isinstance(v, str) else 0


def _excerpt(s: str, n: int = 380) -> str:
    flat = " ".join(str(s or "").split())
    return flat if len(flat) <= n else flat[: n - 1].rstrip() + "…"


def card_info(card: JSONDict, notes: list[str], b64_len: int = 0) -> JSONDict:
    data = card.get("data") if isinstance(card.get("data"), dict) else {}
    assert isinstance(data, dict)
    greetings = [g for g in data.get("alternate_greetings") or [] if isinstance(g, str)]  # type: ignore[union-attr]
    book = data.get("character_book")
    entries = book.get("entries") if isinstance(book, dict) else None
    entry_list = entries if isinstance(entries, list) else []
    chars = sum(_text_len(v) for v in data.values()) + sum(len(g) for g in greetings) + \
        sum(_text_len(e.get("content")) for e in entry_list if isinstance(e, dict))
    tokens = max(1, round(chars / 4))
    rarity = "common" if tokens < 600 else "rare" if tokens < 1800 else "epic" if tokens < 3500 else "legendary"
    tags = data.get("tags")
    return {
        "name": str(data.get("name", "")), "creator": str(data.get("creator", "") or ""),
        "tags": [str(t) for t in tags][:10] if isinstance(tags, list) else [],
        "spec_version": str(card.get("spec_version", "2.0")),
        "chars": {k: _text_len(data.get(k)) for k in ("description", "first_mes", "mes_example")},
        "alt_greetings": len(greetings), "book_entries": len(entry_list), "tokens": tokens,
        "kb": round(b64_len / 1024, 1), "rarity": rarity,
        "excerpt_description": _excerpt(str(data.get("description", "") or "")),
        "excerpt_first_mes": _excerpt(str(data.get("first_mes", "") or "")),
        "notes": list(notes),
    }
