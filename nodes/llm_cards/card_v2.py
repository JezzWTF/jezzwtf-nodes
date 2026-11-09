"""Character Card V2 normalisation for the PNG baker (spec 5.2 and 5.3)."""

from __future__ import annotations

import copy
import json
import re
from typing import TypedDict

from .common import JSONDict, JSONValue, parse_json_text

V2_DEFAULTS: JSONDict = {
    "name": "",
    "description": "",
    "personality": "",
    "scenario": "",
    "first_mes": "",
    "mes_example": "",
    "creator_notes": "",
    "system_prompt": "",
    "post_history_instructions": "",
    "alternate_greetings": [],
    "tags": [],
    "creator": "",
    "character_version": "",
    "extensions": {},
}
STRING_FIELDS = tuple(k for k, v in V2_DEFAULTS.items() if isinstance(v, str))
HINT_KEYS = ("name", "description", "first_mes", "personality")
LEGACY_KEYS = {
    "char_name": "name",
    "char_persona": "description",
    "world_scenario": "scenario",
    "char_greeting": "first_mes",
    "example_dialogue": "mes_example",
}
DESCEND_KEYS = ("character", "card", "char", "result", "output", "json")


class CardError(ValueError):
    pass


class CardChars(TypedDict):
    description: int
    first_mes: int
    mes_example: int


class CardInfo(TypedDict):
    name: str
    creator: str
    tags: list[str]
    spec_version: str
    chars: CardChars
    alt_greetings: int
    book_entries: int
    tokens: int
    kb: float
    rarity: str
    excerpt_description: str
    excerpt_first_mes: str
    notes: list[str]


def _lower_keys(d: dict[str, JSONValue]) -> dict[str, JSONValue]:
    out: dict[str, JSONValue] = {}
    for k, v in d.items():
        lk = str(k).lower()
        if lk not in out:
            out[lk] = v
    return out


def _try_json(s: str) -> tuple[bool, JSONValue]:
    try:
        return True, json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return False, None


def unwrap_card(obj: JSONValue, notes: list[str]) -> JSONValue:
    """Peel wrappers and encodings off pasted card JSON (spec 5.2 step 2)."""
    for _ in range(5):
        if isinstance(obj, str):
            ok, parsed = _try_json(obj.strip())
            if not ok:
                break
            obj = parsed
            notes.append("Decoded double-encoded JSON string.")
            continue
        if isinstance(obj, list):
            if len(obj) == 1:
                obj = obj[0]
                notes.append("Unwrapped a one-item list.")
                continue
            break
        if not isinstance(obj, dict):
            break
        lowered = _lower_keys(obj)
        if list(lowered) != list(obj):
            notes.append("Lower-cased top-level keys.")
        obj = lowered
        data = obj.get("data")
        if isinstance(data, str):
            ok, parsed = _try_json(data)
            if ok:
                obj["data"] = data = parsed
                notes.append("Decoded `data` from a JSON string.")
        if isinstance(data, dict):
            obj["data"] = _lower_keys(data)
            break
        if any(k in obj for k in HINT_KEYS):
            break
        legacy = [k for k in LEGACY_KEYS if k in obj]
        if legacy:
            for old in legacy:
                new = LEGACY_KEYS[old]
                if new not in obj:
                    obj[new] = obj[old]
                del obj[old]
            notes.append("Renamed legacy TavernAI fields (" + ", ".join(legacy) + ").")
            break
        child_key = next((k for k in DESCEND_KEYS if isinstance(obj.get(k), (dict, str))), None)
        if child_key is not None:
            obj = obj[child_key]
            notes.append(f"Used the card inside `{child_key}`.")
            continue
        if len(obj) == 1:
            only_key = next(iter(obj))
            obj = obj[only_key]
            notes.append(f"Used the only value, `{only_key}`.")
            continue
        break
    return obj


def normalise_v2(raw: JSONValue, fill_missing: bool = True) -> tuple[JSONDict, list[str]]:
    """Turn parsed JSON into a Character Card V2 dict. Returns (card, notes)."""
    notes: list[str] = []
    obj = unwrap_card(raw, notes)
    if not isinstance(obj, dict):
        raise CardError(f"The card JSON must be an object, got {type(obj).__name__}.")

    data = obj.get("data")
    if isinstance(data, dict):
        spec = obj.get("spec")
        if spec == "chara_card_v3":
            notes.append("Relabelled a chara_card_v3 card as chara_card_v2.")
        elif spec not in (None, "", "chara_card_v2"):
            notes.append(f"Replaced unknown spec {spec!r} with chara_card_v2.")
        extras = {k: v for k, v in obj.items() if k not in ("spec", "spec_version", "data")}
        card: JSONDict = {"spec": "chara_card_v2", "spec_version": "2.0", "data": dict(data), **extras}
    elif any(k in obj for k in HINT_KEYS):
        card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": dict(obj)}
        notes.append("Wrapped flat card fields in a V2 `data` block.")
    else:
        keys = ", ".join(list(obj)[:12]) or "(none)"
        raise CardError(f"This JSON does not look like a character card. Top-level keys: {keys}")

    d = card["data"]
    assert isinstance(d, dict)
    if fill_missing:
        filled = [k for k in V2_DEFAULTS if d.get(k) is None]
        for k in filled:
            d[k] = copy.deepcopy(V2_DEFAULTS[k])
        if filled:
            notes.append("Filled missing V2 fields: " + ", ".join(filled) + ".")
    _repair_types(d)
    if not str(d.get("name") or "").strip():
        raise CardError("The card has no name (data.name is blank).")
    return card, notes


def _repair_types(d: dict[str, JSONValue]) -> None:
    for k in STRING_FIELDS:
        if k in d and not isinstance(d[k], str):
            d[k] = "" if d[k] is None else str(d[k])
    tags = d.get("tags")
    if isinstance(tags, str):
        d["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    alt = d.get("alternate_greetings")
    if isinstance(alt, str):
        d["alternate_greetings"] = [alt]
    if "extensions" in d and not isinstance(d["extensions"], dict):
        d["extensions"] = {}


def parse_card_text(text: str, fill_missing: bool = True) -> tuple[JSONDict, list[str]]:
    return normalise_v2(parse_json_text(text), fill_missing)


# --------------------------------------------------------------------------- info


def _collapse(s: str, limit: int = 380) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def rarity_for(tokens: int) -> str:
    if tokens < 600:
        return "common"
    if tokens < 1800:
        return "rare"
    if tokens < 3500:
        return "epic"
    return "legendary"


def card_info(card: JSONDict, b64_len: int, notes: list[str]) -> CardInfo:
    d = card.get("data")
    d = d if isinstance(d, dict) else {}

    def s(key: str) -> str:
        v = d.get(key)
        return v if isinstance(v, str) else ""

    alts = [a for a in (d.get("alternate_greetings") or []) if isinstance(a, str)] \
        if isinstance(d.get("alternate_greetings"), list) else []
    book = d.get("character_book")
    entries = book.get("entries") if isinstance(book, dict) else None
    entries = entries if isinstance(entries, list) else []
    total = sum(len(s(k)) for k in STRING_FIELDS) + sum(len(a) for a in alts)
    total += sum(len(e["content"]) for e in entries if isinstance(e, dict) and isinstance(e.get("content"), str))
    tokens = max(1, round(total / 4))
    tags = d.get("tags")
    return {
        "name": s("name"),
        "creator": s("creator"),
        "tags": [str(t) for t in tags[:10]] if isinstance(tags, list) else [],
        "spec_version": str(card.get("spec_version") or "2.0"),
        "chars": {"description": len(s("description")), "first_mes": len(s("first_mes")),
                  "mes_example": len(s("mes_example"))},
        "alt_greetings": len(alts),
        "book_entries": len(entries),
        "tokens": tokens,
        "kb": round(b64_len / 1024, 1),
        "rarity": rarity_for(tokens),
        "excerpt_description": _collapse(s("description")),
        "excerpt_first_mes": _collapse(s("first_mes")),
        "notes": list(notes),
    }
